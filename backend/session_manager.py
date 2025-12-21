import logging
from typing import Dict, Optional, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory session storage
SESSION_STATE: Dict[str, Dict[str, Any]] = {}


def create_session(session_id: str) -> Dict[str, Any]:
    """Initialize a new session with empty data"""
    try:
        if session_id in SESSION_STATE:
            logger.info(f"Session {session_id} already exists")
            return SESSION_STATE[session_id]
        
        SESSION_STATE[session_id] = {
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
            # NEW: Multi-turn information collection fields
            "reason_for_action": None,  # Why user wants refund/replacement
            "purchase_date_confirmed": None,  # User's stated purchase date
            "preferred_datetime": None,  # For service booking date/time
            "additional_details": None,  # Any extra context
            "required_info_collected": False,  # Flag for completeness
            "conversation_history": [],
            # Conversation state management
            "conversation_state": "collecting_info",  # collecting_info, ready_for_action, action_executed, completed
            "action_id": None,
            "action_type": None
        }
        
        logger.info(f"Created new session: {session_id}")
        return SESSION_STATE[session_id]
        
    except Exception as e:
        logger.error(f"ERROR: Error creating session: {e}")
        return {}


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session data or create if doesn't exist"""
    try:
        if session_id not in SESSION_STATE:
            logger.info(f"Session {session_id} not found, creating new one")
            return create_session(session_id)
        
        return SESSION_STATE[session_id]
        
    except Exception as e:
        logger.error(f"ERROR: Error retrieving session: {e}")
        return None


def update_session(session_id: str, key: str, value: Any) -> bool:
    """Update a specific field in the session"""
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id)
        
        SESSION_STATE[session_id][key] = value
        logger.info(f"Updated session {session_id}: {key} = {value}")
        return True
        
    except Exception as e:
        logger.error(f"ERROR: Error updating session: {e}")
        return False


def update_session_bulk(session_id: str, data: Dict[str, Any]) -> bool:
    """Update multiple fields in the session at once"""
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id)
        
        for key, value in data.items():
            SESSION_STATE[session_id][key] = value
        
        logger.info(f"Bulk updated session {session_id} with {len(data)} fields")
        return True
        
    except Exception as e:
        logger.error(f"ERROR: Error bulk updating session: {e}")
        return False


def add_to_conversation_history(session_id: str, role: str, message: str):
    """Add a message to the conversation history"""
    try:
        if session_id not in SESSION_STATE:
            create_session(session_id)
        
        SESSION_STATE[session_id]["conversation_history"].append({
            "role": role,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"ERROR: Error adding to conversation history: {e}")


def clear_session(session_id: str) -> bool:
    """Clear session data"""
    try:
        if session_id in SESSION_STATE:
            del SESSION_STATE[session_id]
            logger.info(f"Cleared session: {session_id}")
            return True
        
        logger.warning(f"Session {session_id} not found")
        return False
        
    except Exception as e:
        logger.error(f"ERROR: Error clearing session: {e}")
        return False


def get_session_context(session_id: str) -> str:
    """Get formatted session context for agent prompts"""
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
        
        if session.get("issue_description"):
            context_parts.append(f"Issue: {session['issue_description']}")
        
        if context_parts:
            return "Known Information:\n" + "\n".join(f"- {part}" for part in context_parts)
        
        return ""
        
    except Exception as e:
        logger.error(f"ERROR: Error getting session context: {e}")
        return ""


def set_conversation_state(session_id: str, state: str) -> bool:
    """Set conversation state: collecting_info, ready_for_action, action_executed, completed"""
    try:
        valid_states = ["collecting_info", "ready_for_action", "action_executed", "completed"]
        if state not in valid_states:
            logger.error(f"Invalid state: {state}")
            return False
        
        return update_session(session_id, "conversation_state", state)
    except Exception as e:
        logger.error(f"ERROR: Error setting conversation state: {e}")
        return False


def get_conversation_state(session_id: str) -> str:
    """Get current conversation state"""
    try:
        session = get_session(session_id)
        return session.get("conversation_state", "collecting_info") if session else "collecting_info"
    except Exception as e:
        logger.error(f"ERROR: Error getting conversation state: {e}")
        return "collecting_info"


def is_info_complete(session_id: str) -> bool:
    """Check if all required information has been collected"""
    try:
        session = get_session(session_id)
        if not session:
            return False
        
        # Required: order_id OR (customer info + product info)
        has_order_id = session.get("order_id") is not None
        has_customer = session.get("customer_name") is not None
        has_product = session.get("product_name") is not None
        
        # At minimum need either order_id or customer+product
        return has_order_id or (has_customer and has_product)
    except Exception as e:
        logger.error(f"ERROR: Error checking info completeness: {e}")
        return False


def mark_action_completed(session_id: str, action_id: str, action_type: str) -> bool:
    """Mark that an action has been completed"""
    try:
        if session_id not in SESSION_STATE:
            return False
        
        SESSION_STATE[session_id]["action_id"] = action_id
        SESSION_STATE[session_id]["action_type"] = action_type
        SESSION_STATE[session_id]["conversation_state"] = "action_executed"
        
        logger.info(f"Marked action completed: {action_type} - {action_id}")
        return True
    except Exception as e:
        logger.error(f"ERROR: Error marking action completed: {e}")
        return False


def get_all_sessions():
    """Get all active sessions (for debugging)"""
    return SESSION_STATE


def check_missing_info_for_action(session_id: str, action_type: str) -> dict:
    """Check what information is missing for completing an action
    
    Requirements:
    - Refund/Replacement: 2 questions (Order ID + Reason)
    - Service Booking: 2 questions (Order ID + Preferred Date/Time)
    
    Returns:
        {
            "missing": ["field1", "field2"],  # List of missing fields
            "complete": bool,  # True if all required info is present
            "prompt": str  # Suggested question to ask user
        }
    """
    try:
        session = get_session(session_id)
        if not session:
            return {"missing": ["all"], "complete": False, "prompt": "Could you please provide your Order ID?"}
        
        missing = []
        
        # Check for Order ID (required for all actions)
        if not session.get("order_id"):
            missing.append("order_id")
        
        # Check for Reason (required for refund/replacement - 2nd question)
        if action_type in ["initiate_refund", "initiate_replacement"]:
            if not session.get("reason_for_action"):
                missing.append("reason_for_action")
        
        # Check for Service Date/Time (required for service booking - 2nd question)
        if action_type == "book_service":
            if not session.get("preferred_datetime"):
                missing.append("preferred_datetime")
        
        # Generate prompt based on what's missing (prioritize in order)
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
        
        is_complete = len(missing) == 0
        
        return {
            "missing": missing,
            "complete": is_complete,
            "prompt": prompt
        }
        
    except Exception as e:
        logger.error(f"ERROR: Error checking missing info: {e}")
        return {"missing": ["unknown"], "complete": False, "prompt": "Could you provide your Order ID?"}
