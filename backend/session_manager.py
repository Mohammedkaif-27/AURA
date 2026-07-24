"""
AURA Backend — Session Manager

Purpose:
    Track the state of each customer conversation across the chat
    lifecycle.  Stores order context, collected information, and
    conversation history.

Responsibilities:
    - Create / retrieve / update chat sessions
    - Persist messages to Supabase (survives server restarts)
    - Keep in-memory state for temporary workflow variables
      (reason_for_action, preferred_datetime, etc.)
    - Check what information is still missing before executing actions
    - Build formatted context strings for agent prompts

Architecture:
    There are TWO layers of session storage:

    ┌──────────────────────────────────────────────────┐
    │  In-Memory (SESSION_STATE dict)                  │
    │  - Fast reads/writes                             │
    │  - Holds temporary workflow vars                 │
    │  - Lost on server restart                        │
    └──────────────────────────────────────────────────┘
                        │
                        ▼
    ┌──────────────────────────────────────────────────┐
    │  Supabase (chat_sessions + chat_messages tables) │
    │  - Persistent across restarts                    │
    │  - Row-Level Security per user                   │
    │  - Stores message history + session metadata     │
    └──────────────────────────────────────────────────┘

    Why both?
        In-memory state is fast and holds workflow-specific variables
        (like "reason_for_action") that don't need to persist to the DB.
        Supabase stores the durable data (messages, session title) so
        chat history survives server restarts.

Used By:
    orchestrator.py  (every message goes through session manager)
    main.py          (session CRUD endpoints)

Depends On:
    supabase_client.py

Related Files:
    orchestrator.py     — reads/writes session state during chat
    main.py             — /chat/sessions endpoints
    supabase_client.py  — database operations
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime
from . import supabase_client
import json

logger = logging.getLogger(__name__)


# ==========================================================
# IN-MEMORY SESSION STATE
# ==========================================================
# Why in-memory?
# Temporary workflow variables (reason_for_action, preferred_datetime)
# are only needed during the current conversation.  Persisting them
# to the DB on every update would be slow and unnecessary.
SESSION_STATE: Dict[str, Dict[str, Any]] = {}


# ==========================================================
# HELPERS
# ==========================================================

def get_user_supabase(user: dict):
    """Get a user-scoped Supabase client (for RLS)."""
    if not user or "token" not in user:
        return None
    return supabase_client.get_user_client(user["token"])


def _default_session(session_id: str) -> Dict[str, Any]:
    """Return a fresh session dict with all fields set to defaults."""
    return {
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "order_id": None,
        "customer_name": None,
        "customer_email": None,
        "customer_phone": None,
        "product_id": None,
        "product_name": None,
        "model_number": None,
        "serial_number": None,
        "purchase_date": None,
        "warranty_years": None,
        "issue_description": None,
        "reason_for_action": None,
        "purchase_date_confirmed": None,
        "preferred_datetime": None,
        "additional_details": None,
        "required_info_collected": False,
        "conversation_history": [],
        "conversation_state": "collecting_info",
        "action_id": None,
        "action_type": None,
    }


# ==========================================================
# SESSION LIFECYCLE  (create / get / update)
# ==========================================================

def create_session(session_id: str, user: dict = None) -> Dict[str, Any]:
    """
    Initialize a new session.

    Why UPSERT?
        After a server restart, the session may already exist in
        Supabase but not in memory.  Using UPSERT (instead of INSERT)
        prevents 409 duplicate-key errors.

    Called By:  get_session(), orchestrator.py
    Returns:   The session dict.
    """
    try:
        if session_id in SESSION_STATE:
            return SESSION_STATE[session_id]

        SESSION_STATE[session_id] = _default_session(session_id)
        if user and "email" in user:
            SESSION_STATE[session_id]["customer_email"] = user["email"]

        # Persist to Supabase using UPSERT
        client = get_user_supabase(user)
        if client:
            try:
                client.table("chat_sessions").upsert({
                    "session_id": session_id,
                    "user_id": user["user_id"],
                    "title": "New Chat",
                    "status": "active"
                }, on_conflict="session_id").execute()
            except Exception as db_e:
                logger.error(f"Failed to save session to DB: {db_e}")

        logger.info(f"Session created: {session_id}")
        return SESSION_STATE[session_id]

    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return {}


def get_session(session_id: str, user: dict = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve session data — checks in-memory first, then Supabase.

    Why check Supabase?
        On server restart, in-memory state is empty.  This function
        checks Supabase before creating a brand-new session, so the
        user's existing chat history is preserved.

    Called By:  orchestrator.py (every message), get_session_context(),
               check_missing_info_for_action()
    Returns:   Session dict, or None on error.
    """
    try:
        # In-memory hit
        if session_id in SESSION_STATE:
            return SESSION_STATE[session_id]

        # Check Supabase before creating (survives server restarts)
        client = get_user_supabase(user)
        if client:
            try:
                res = client.table("chat_sessions").select("*").eq("session_id", session_id).execute()
                if res.data and len(res.data) > 0:
                    # Session exists in DB — rehydrate in-memory state
                    SESSION_STATE[session_id] = _default_session(session_id)
                    if user and "email" in user:
                        SESSION_STATE[session_id]["customer_email"] = user["email"]
                    logger.info(f"Session rehydrated from DB: {session_id}")
                    return SESSION_STATE[session_id]
            except Exception as db_e:
                logger.warning(f"DB session lookup failed: {db_e}")

        # Truly new session
        return create_session(session_id, user)

    except Exception as e:
        logger.error(f"Error retrieving session: {e}")
        return None


def update_session(session_id: str, key: str, value: Any) -> bool:
    """Update a specific field in the session."""
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id)
        SESSION_STATE[session_id][key] = value
        return True
    except Exception as e:
        logger.error(f"Error updating session: {e}")
        return False


def update_session_bulk(session_id: str, data: Dict[str, Any]) -> bool:
    """Update multiple fields in the session at once."""
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id)
        for key, value in data.items():
            SESSION_STATE[session_id][key] = value
        return True
    except Exception as e:
        logger.error(f"Error bulk updating session: {e}")
        return False


# ==========================================================
# CONVERSATION HISTORY
# ==========================================================

def add_to_conversation_history(session_id: str, role: str, message: str, user: dict = None, sources: list = None):
    """
    Append a message to the conversation and persist it to Supabase.

    Also auto-titles the session based on the first user message
    (e.g. "How do I clean my air pur..." becomes the sidebar title).

    Called By:  orchestrator.py (after each user/assistant message)
    """
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id, user)

        SESSION_STATE[session_id]["conversation_history"].append({
            "role": role,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

        # Persist to DB
        client = get_user_supabase(user)
        if client:
            client.table("chat_messages").insert({
                "session_id": session_id,
                "role": role,
                "content": message,
                "sources": sources or []
            }).execute()

            # Auto-title on first user message
            if role == "user" and len(SESSION_STATE[session_id]["conversation_history"]) <= 2:
                title = message[:30] + "..." if len(message) > 30 else message
                client.table("chat_sessions").update(
                    {"title": title, "updated_at": datetime.now().isoformat()}
                ).eq("session_id", session_id).execute()

    except Exception as e:
        logger.error(f"Error adding to conversation history: {e}")


# ==========================================================
# CONTEXT GENERATION (for agent prompts)
# ==========================================================

def get_session_context(session_id: str) -> str:
    """
    Build a formatted string of everything we know about the customer.

    Why?
        The LLM has no memory between requests.  This function collects
        all known order/customer data and formats it so the LLM can
        reference it when generating a response.

    Called By:  orchestrator.py → process_message()
    Returns:   A formatted string like "Known Information:\\n- Order ID: ORD301\\n..."
    """
    try:
        session = get_session(session_id)
        if not session:
            return ""

        context_parts = []

        if session.get("order_id"):
            context_parts.append(f"Order ID: {session['order_id']}")
        if session.get("customer_name"):
            context_parts.append(f"Customer: {session['customer_name']}")
        if session.get("product_name"):
            context_parts.append(f"Product: {session['product_name']}")
        if session.get("model_number"):
            context_parts.append(f"Model: {session['model_number']}")
        if session.get("status"):
            context_parts.append(f"Status: {session['status']}")
        if session.get("purchase_date"):
            context_parts.append(f"Purchase Date: {session['purchase_date']}")
        if session.get("warranty_years") is not None:
            context_parts.append(f"Warranty: {session['warranty_years']} years")
        if session.get("issue_description"):
            context_parts.append(f"Issue: {session['issue_description']}")

        if context_parts:
            return "Known Information:\n" + "\n".join(f"- {part}" for part in context_parts)

        return ""

    except Exception as e:
        logger.error(f"Error getting session context: {e}")
        return ""


# ==========================================================
# ACTION TRACKING
# ==========================================================

def mark_action_completed(session_id: str, action_id: str, action_type: str) -> bool:
    """Record that an action (refund/replacement/service) was executed."""
    try:
        if session_id not in SESSION_STATE:
            return False
        SESSION_STATE[session_id]["action_id"] = action_id
        SESSION_STATE[session_id]["action_type"] = action_type
        SESSION_STATE[session_id]["conversation_state"] = "action_executed"
        logger.info(f"Action completed: {action_type} — {action_id}")
        return True
    except Exception as e:
        logger.error(f"Error marking action completed: {e}")
        return False


# ==========================================================
# VALIDATION  (pre-action checks)
# ==========================================================

def check_missing_info_for_action(session_id: str, action_type: str) -> dict:
    """
    Check what information is still missing before executing an action.

    Why?
        Before processing a refund, replacement, or service booking,
        we need specific data (Order ID, reason, date/time).  This
        function tells the orchestrator what to ask the user next.

    Requirements by action type:
        - Refund / Replacement:  Order ID + Reason
        - Service Booking:       Order ID + Preferred Date/Time

    Called By:  orchestrator.py → process_message() (action branch)
    Returns:   {"missing": [...], "complete": bool, "prompt": str}
    """
    try:
        session = get_session(session_id)
        if not session:
            return {"missing": ["all"], "complete": False, "prompt": "Could you please provide your Order ID?"}

        missing = []

        if not session.get("order_id"):
            missing.append("order_id")

        if action_type in ["initiate_refund", "initiate_replacement"]:
            if not session.get("reason_for_action"):
                missing.append("reason_for_action")

        if action_type == "book_service":
            if not session.get("preferred_datetime"):
                missing.append("preferred_datetime")

        # Generate prompt based on what's missing
        prompt = ""
        if "order_id" in missing:
            prompt = "To process your request, I'll need your **Order ID** (e.g., ORD301)."
        elif "reason_for_action" in missing:
            if action_type == "initiate_refund":
                prompt = "Could you tell me the reason for your refund request?"
            elif action_type == "initiate_replacement":
                prompt = "What issue are you experiencing with the product?"
        elif "preferred_datetime" in missing:
            prompt = "When would you prefer the service? Please provide a date and time (e.g., 'December 24, 2025 at 2:00 PM')."

        return {
            "missing": missing,
            "complete": len(missing) == 0,
            "prompt": prompt
        }

    except Exception as e:
        logger.error(f"Error checking missing info: {e}")
        return {"missing": ["unknown"], "complete": False, "prompt": "Could you provide your Order ID?"}
