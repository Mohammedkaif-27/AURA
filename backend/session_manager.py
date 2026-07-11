"""
AURA Session Manager — Manages chat session state and persistence.

OPTIMIZED:
- Sessions survive server restarts via Supabase check-before-create.
- Uses UPSERT to prevent 409 duplicate key errors.
- Reduced noisy per-field logging.
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime
from . import supabase_client
import json

logger = logging.getLogger(__name__)

# In-memory state for temporary workflow vars (reason_for_action, etc.)
# Base session and messages are persisted to Supabase.
SESSION_STATE: Dict[str, Dict[str, Any]] = {}


def get_user_supabase(user: dict):
    """Get a user-scoped Supabase client."""
    if not user or "token" not in user:
        return None
    return supabase_client.get_user_client(user["token"])


def _default_session(session_id: str) -> Dict[str, Any]:
    """Return a fresh session dict with defaults."""
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


def create_session(session_id: str, user: dict = None) -> Dict[str, Any]:
    """Initialize a new session with empty data.

    Uses UPSERT to prevent 409 duplicate key errors after server restarts.
    """
    try:
        if session_id in SESSION_STATE:
            return SESSION_STATE[session_id]

        SESSION_STATE[session_id] = _default_session(session_id)
        if user and "email" in user:
            SESSION_STATE[session_id]["customer_email"] = user["email"]

        # Persist to Supabase using UPSERT (prevents duplicate key errors)
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
    """Retrieve session data — checks in-memory first, then Supabase.

    On server restart, in-memory state is lost. This function checks
    Supabase before creating a new session to avoid duplicates.
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


def add_to_conversation_history(session_id: str, role: str, message: str, user: dict = None, sources: list = None):
    """Add a message to the conversation history and persist to Supabase."""
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


def clear_session(session_id: str) -> bool:
    """Clear session data."""
    try:
        if session_id in SESSION_STATE:
            del SESSION_STATE[session_id]
            return True
        return False
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return False


def get_session_context(session_id: str) -> str:
    """Get formatted session context for agent prompts."""
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


def set_conversation_state(session_id: str, state: str) -> bool:
    """Set conversation state: collecting_info, ready_for_action, action_executed, completed."""
    valid_states = ["collecting_info", "ready_for_action", "action_executed", "completed"]
    if state not in valid_states:
        logger.error(f"Invalid state: {state}")
        return False
    return update_session(session_id, "conversation_state", state)


def get_conversation_state(session_id: str) -> str:
    """Get current conversation state."""
    session = get_session(session_id)
    return session.get("conversation_state", "collecting_info") if session else "collecting_info"


def is_info_complete(session_id: str) -> bool:
    """Check if all required information has been collected."""
    session = get_session(session_id)
    if not session:
        return False
    has_order_id = session.get("order_id") is not None
    has_customer = session.get("customer_name") is not None
    has_product = session.get("product_name") is not None
    return has_order_id or (has_customer and has_product)


def mark_action_completed(session_id: str, action_id: str, action_type: str) -> bool:
    """Mark that an action has been completed."""
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


def get_all_sessions():
    """Get all active sessions (for debugging)."""
    return SESSION_STATE


def check_missing_info_for_action(session_id: str, action_type: str) -> dict:
    """Check what information is missing for completing an action.

    Requirements:
    - Refund/Replacement: Order ID + Reason
    - Service Booking: Order ID + Preferred Date/Time
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
