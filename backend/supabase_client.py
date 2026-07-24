"""
AURA Backend — Supabase Client

Purpose:
    Centralized data access layer for all Supabase operations.
    Every database read/write in the backend goes through this module.

Responsibilities:
    - Initialize and cache the Supabase client (service role)
    - Provide user-scoped clients for Row-Level Security (RLS)
    - CRUD operations for: Products, Orders, Policies, Knowledge Base,
      Refunds, Chat Sessions
    - File operations: upload, download, list (Supabase Storage)
    - Policy resolution: category override → global fallback

Architecture:
    There are TWO types of Supabase clients:

    ┌──────────────────────────────────────────────────┐
    │  Service Role Client  (_get_client)              │
    │  - Uses SUPABASE_SERVICE_ROLE_KEY                │
    │  - Bypasses Row-Level Security                   │
    │  - Used for: admin operations, background tasks  │
    └──────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────┐
    │  User-Scoped Client  (get_user_client)           │
    │  - Uses SUPABASE_ANON_KEY + user's JWT           │
    │  - Enforces Row-Level Security                   │
    │  - Used for: chat sessions, messages (per-user)  │
    └──────────────────────────────────────────────────┘

    Why two clients?
        RLS ensures users can only see their own chat history.
        But admin/background tasks (like re-indexing documents)
        need full access, so they use the service role key.

Used By:
    main.py             — admin endpoints, startup tasks
    session_manager.py  — chat session persistence
    order_lookup.py     — order retrieval
    sync_manuals.py     — manual sync utility
    orchestrator.py     — policy resolution during action execution

Depends On:
    supabase-py

Related Files:
    supabase_schema.sql — database schema (tables, RLS policies)
    .env                — SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ==========================================================
# CLIENT INITIALIZATION
# ==========================================================

_client = None
_initialized = False


def _get_client():
    """
    Lazy-initialize the service-role Supabase client.

    Why lazy?
        The client is only created on first use, not at import time.
        This prevents crashes if Supabase credentials are missing
        during development or testing.
    """
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        missing = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        msg = (
            f"Supabase credentials missing: {', '.join(missing)}. "
            f"Create a free project at https://supabase.com, run supabase_schema.sql, "
            f"and set these values in your .env file. "
            f"Falling back to local JSON (limited functionality)."
        )
        logger.warning(msg)
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        logger.info("Supabase client initialized successfully")
        return _client
    except ImportError:
        logger.warning("supabase-py not installed — pip install supabase")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None


def get_user_client(access_token: str):
    """
    Create a user-scoped Supabase client for RLS enforcement.

    Why?
        Row-Level Security (RLS) policies in Supabase use the JWT
        to determine which rows a user can access.  By setting the
        user's session token on the client, all queries automatically
        filter to that user's data.

    Called By:  session_manager.py → get_user_supabase()
    """
    url = os.getenv("SUPABASE_URL", "")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not anon_key:
        logger.error("SUPABASE_URL or SUPABASE_ANON_KEY missing for user client")
        return None

    try:
        from supabase import create_client
        client = create_client(url, anon_key)
        client.auth.set_session(access_token, "dummy_refresh_token")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize user-scoped Supabase client: {e}")
        return None


# ==========================================================
# PRODUCTS
# ==========================================================

def get_products():
    """Fetch all products."""
    client = _get_client()
    if not client:
        return []
    try:
        result = client.table("products").select("*").execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        return []


def get_product_by_id(product_id: str):
    """Fetch a single product by ID."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("products").select("*").eq("id", product_id).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        return None


def upsert_product(product_data: dict):
    """Insert or update a product."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("products").upsert(product_data).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error upserting product: {e}")
        return None


def delete_product(product_id: str):
    """Delete a product by ID."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("products").delete().eq("id", product_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting product {product_id}: {e}")
        return False


# ==========================================================
# ORDERS
# ==========================================================

def get_orders():
    """Fetch all orders, newest first."""
    client = _get_client()
    if not client:
        return []
    try:
        result = client.table("orders").select("*").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return []


def get_order_by_id_db(order_id: str):
    """
    Fetch a single order by ID, with hyphen-fallback.

    Why the fallback?
        Users might type "ORD2097" instead of "ORD-2097".
        If exact match fails, we retry with a hyphen inserted.
    """
    client = _get_client()
    if not client:
        return None
    try:
        try:
            result = client.table("orders").select("*").eq("id", order_id).single().execute()
            return result.data
        except Exception as e:
            # If not found (PGRST116), try inserting a hyphen
            if 'PGRST116' in str(e) and '-' not in order_id and order_id.startswith('ORD'):
                hyphenated = order_id.replace('ORD', 'ORD-')
                try:
                    result2 = client.table("orders").select("*").eq("id", hyphenated).single().execute()
                    return result2.data
                except Exception:
                    pass
            logger.error(f"Error fetching order {order_id}: {e}")
            return None
    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {e}")
        return None


def insert_order(order_data: dict):
    """Insert a new order."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("orders").insert(order_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error inserting order: {e}")
        raise


def update_order(order_id: str, order_data: dict):
    """Update an existing order."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("orders").update(order_data).eq("id", order_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error updating order {order_id}: {e}")
        raise


def delete_order(order_id: str):
    """Delete an order by ID."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("orders").delete().eq("id", order_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting order {order_id}: {e}")
        return False


# ==========================================================
# POLICIES
# ==========================================================

def get_policies():
    """Fetch all policies, newest first."""
    client = _get_client()
    if not client:
        return []
    try:
        result = client.table("policies").select("*").order("updated_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching policies: {e}")
        return []


def get_policy_by_id(policy_id: str):
    """Fetch a single policy by ID."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("policies").select("*").eq("id", policy_id).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching policy {policy_id}: {e}")
        return None


def upsert_policy(policy_data: dict):
    """Insert or update a policy."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("policies").upsert(policy_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error upserting policy: {e}")
        raise


def delete_policy(policy_id: str):
    """Delete a policy by ID."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("policies").delete().eq("id", policy_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting policy {policy_id}: {e}")
        return False


def resolve_policy(category: str, policy_type: str) -> dict:
    """
    Deterministic policy resolution: category override > global fallback.

    Why?
        Business policies (refund windows, replacement rules) can be
        set globally OR overridden per product category.  This function
        checks for a category-specific policy first, then falls back
        to the global default.

    Called By:  orchestrator.py (during action execution)
    Returns:   Policy dict with 'rules' JSONB, or None.
    """
    client = _get_client()
    if not client:
        return None
    try:
        # 1. Try category-specific override first
        if category:
            result = (
                client.table("policies")
                .select("*")
                .eq("scope", "category")
                .eq("category", category)
                .eq("policy_type", policy_type)
                .execute()
            )
            if result.data and len(result.data) > 0:
                logger.info(f"Resolved {policy_type} policy: category override for '{category}'")
                return result.data[0]

        # 2. Fall back to global
        result = (
            client.table("policies")
            .select("*")
            .eq("scope", "global")
            .eq("policy_type", policy_type)
            .execute()
        )
        if result.data and len(result.data) > 0:
            logger.info(f"Resolved {policy_type} policy: global fallback")
            return result.data[0]

        logger.warning(f"No policy found for type={policy_type}, category={category}")
        return None
    except Exception as e:
        logger.error(f"Error resolving policy: {e}")
        return None


# ==========================================================
# KNOWLEDGE BASE
# ==========================================================

def get_knowledge_entries():
    """Fetch all knowledge base entries."""
    client = _get_client()
    if not client:
        return []
    try:
        result = client.table("knowledge_base").select("*").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching knowledge base: {e}")
        return []


def insert_knowledge_entry(entry: dict):
    """Insert a new knowledge base entry."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("knowledge_base").insert(entry).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error inserting knowledge entry: {e}")
        return None


def update_knowledge_status(entry_id: int, status: str, chunks_count: int = 0):
    """Update knowledge base entry status after indexing."""
    client = _get_client()
    if not client:
        return None
    try:
        update_data = {"status": status}
        if chunks_count:
            update_data["chunks_count"] = chunks_count
        if status == "ready":
            from datetime import datetime
            update_data["last_indexed"] = datetime.now().isoformat()

        result = client.table("knowledge_base").update(update_data).eq("id", entry_id).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error updating knowledge status: {e}")
        return None


# ==========================================================
# REFUNDS
# ==========================================================

def insert_refund(refund_data: dict):
    """Insert a refund record."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("refunds").insert(refund_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error inserting refund: {e}")
        return None


# ==========================================================
# CHAT SESSIONS
# ==========================================================

def get_active_sessions():
    """Fetch all active/handed-over chat sessions."""
    client = _get_client()
    if not client:
        return []
    try:
        result = (
            client.table("chat_sessions")
            .select("*")
            .in_("status", ["active", "handed_over"])
            .order("updated_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return []


def update_session_status(session_id: str, status: str):
    """Update session status (active / handed_over / closed)."""
    client = _get_client()
    if not client:
        return None
    try:
        result = (
            client.table("chat_sessions")
            .update({"status": status})
            .eq("session_id", session_id)
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        return None


# ==========================================================
# SUPABASE STORAGE (file uploads / downloads)
# ==========================================================

def upload_file_to_storage(bucket: str, path: str, file_bytes: bytes, content_type: str = "application/pdf"):
    """Upload a file to Supabase Storage."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.storage.from_(bucket).upload(path, file_bytes, {"content-type": content_type})
        return result
    except Exception as e:
        logger.error(f"Error uploading to storage: {e}")
        return None


def get_storage_file_list(bucket: str, folder: str = "") -> list:
    """List all files in a Supabase Storage bucket/folder."""
    client = _get_client()
    if not client:
        return []
    try:
        result = client.storage.from_(bucket).list(folder)
        return result or []
    except Exception as e:
        logger.error(f"Error listing storage files: {e}")
        return []


def download_file_from_storage(bucket: str, path: str) -> bytes:
    """Download a file from Supabase Storage. Returns raw bytes or None."""
    client = _get_client()
    if not client:
        return None
    try:
        data = client.storage.from_(bucket).download(path)
        return data
    except Exception as e:
        logger.error(f"Error downloading from storage ({path}): {e}")
        return None
