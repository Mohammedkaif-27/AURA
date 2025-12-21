import os
import logging
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from .rag import search_knowledge

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Initialize Vertex AI with error handling
try:
    aiplatform.init(
        project=PROJECT_ID,
        location=REGION
    )
    # Try using Gemini 2.0 Flash which is generally available
    model = GenerativeModel("gemini-2.0-flash-001")
    logger.info("Vertex AI initialized successfully")
except Exception as e:
    logger.error(f"ERROR: Failed to initialize Vertex AI: {e}")
    model = None


# ---------------- INTENT AGENT ----------------
def intent_agent(user_message):
    """Classify user intent - returns only the intent label"""
    try:
        if not model:
            logger.error("Model not initialized")
            return "general_query"
        
        prompt = f"""You are an intent classification agent for a customer support system.

Your task is to classify the user query into exactly ONE of the following intent labels:

- troubleshoot
- refund
- replacement
- service_booking
- order_status
- product_information
- general_query

Rules:
- Choose only ONE label.
- Do not explain your answer.
- Do not add extra text.
- Output only the label.

User query:
{user_message}"""
        
        resp = model.generate_content(prompt)
        intent = resp.text.strip().lower()
        
        # Validate intent
        valid_intents = ["troubleshoot", "refund", "replacement", "service_booking", 
                        "order_status", "product_information", "general_query"]
        
        if intent not in valid_intents:
            logger.warning(f"Invalid intent '{intent}', defaulting to general_query")
            intent = "general_query"
        
        logger.info(f"Intent classified: {intent}")
        return intent
            
    except Exception as e:
        logger.error(f"ERROR: Intent agent error: {e}")
        return "general_query"


# ---------------- RETRIEVAL AGENT ----------------
def retrieval_agent(query):
    """Retrieve relevant context from knowledge base"""
    try:
        # Primary RAG-based retrieval
        docs = search_knowledge(query)
        context = "\n\n".join(docs) if docs else ""
        logger.info(f"Retrieved {len(docs)} documents")
        return context
    except Exception as e:
        logger.error(f"ERROR: Retrieval agent error: {e}")
        return ""


# ---------------- RESPONDER AGENT ----------------
def responder_agent(context, message, session_context=""):
    """Generate the main human-like reply"""
    try:
        if not model:
            logger.error("Model not initialized")
            return "I apologize, but I'm experiencing technical difficulties. Please try again later."
        
        prompt = f"""You are AURA, a professional and empathetic customer support executive.

Your job is to answer the user accurately using ONLY the provided context.
If the context is insufficient, clearly state what additional information is required.

{session_context}

CRITICAL RULES:
- Be clear, polite, and professional.
- Respond in the SAME language as the user.
- Provide step-by-step guidance if troubleshooting.
- Do not invent facts, policies, or procedures.
- DO NOT ask for information already mentioned in "Known Information" above
- Only ask for information that is truly missing and required

Context:
{context if context else "No context available"}

User query:
{message}"""
        
        res = model.generate_content(prompt)
        response_text = res.text.strip()
        
        logger.info(f"Response generated ({len(response_text)} chars)")
        return response_text
        
    except Exception as e:
        logger.error(f"ERROR: Responder agent error: {e}")
        return "I apologize, but I'm having trouble processing your request. Please try again."


# ---------------- VERIFIER AGENT ----------------
def verifier_agent(draft_response, context=""):
    """Verify draft response quality and accuracy
    
    Simplified: Returns draft response if API fails (quota exhaustion)
    """
    try:
        if not model:
            logger.warning("Model not initialized in verifier")
            return draft_response  # Return draft as-is
        
        prompt = f"""You are a response quality verifier.

Context:
{context}

Draft Response:
{draft_response}

Task: Verify if the draft response is accurate, helpful, and professional.
If it's good, return it unchanged. If it needs minor fixes, return the corrected version.

Rules:
- Keep the tone professional and friendly
- Ensure accuracy
- Only output the final response text (no explanations)"""

        res = model.generate_content(prompt)
        verified = res.text.strip()
        logger.info("Response verified")
        return verified
        
    except Exception as e:
        logger.error(f"ERROR: Verifier agent error: {e}")
        # Return draft response if verification fails (API quota issue)
        return draft_response  # Return original if verification fails


# ---------------- ACTION AGENT ----------------
def action_agent(intent, verified_response):
    """Decide whether a real operational action is required
    
    DETERMINISTIC VERSION: Maps intent directly to action (no API call)
    This avoids quota exhaustion issues with Vertex AI
    """
    try:
        # Direct intent-to-action mapping (no LLM needed)
        intent_to_action = {
            "refund": "initiate_refund",
            "replacement": "initiate_replacement",
            "service_booking": "book_service",
            "order_status": "none",
            "product_information": "none",
            "troubleshoot": "none",
            "general_query": "none"
        }
        
        # Get action from mapping
        action = intent_to_action.get(intent, "none")
        
        logger.info(f"Action decided (deterministic): {action} (from intent: {intent})")
        return action
        
    except Exception as e:
        logger.error(f"ERROR: Action agent error: {e}")
        return "none"


# ---------------- ACTION CONFIRMATION AGENT (Optional) ----------------
def action_confirmation_agent(action_type):
    """Ask user consent before executing an operational action"""
    try:
        if action_type == "none":
            return None
        
        if not model:
            return f"To proceed with {action_type}, please confirm."
        
        prompt = f"""You are confirming an operational action with the customer.

Politely ask for confirmation to proceed.
Clearly explain what will happen next.

Action:
{action_type}"""
        
        res = model.generate_content(prompt)
        confirmation_message = res.text.strip()
        
        logger.info(f"Confirmation message generated for: {action_type}")
        return confirmation_message
        
    except Exception as e:
        logger.error(f"ERROR: Action confirmation error: {e}")
        return f"To proceed with {action_type}, please confirm."


# ---------------- ACTION EXECUTION ----------------
def generate_action_id(action_type: str) -> str:
    """Generate unique action ID in format: REF-YYYYMMDD-XXXX"""
    try:
        from datetime import datetime
        from pathlib import Path
        import json

        date_str = datetime.now().strftime("%Y%m%d")
        
        # Determine prefix and file path
        if action_type == "initiate_refund":
            prefix = "REF"
            file_path = Path(__file__).parent / "data" / "refunds.json"
        elif action_type == "initiate_replacement":
            prefix = "REP"
            file_path = Path(__file__).parent / "data" / "replacements.json"
        elif action_type == "book_service":
            prefix = "SRV"
            file_path = Path(__file__).parent / "data" / "service_bookings.json"
        else:
            return f"ACTION-{date_str}-0001"
        
        # Read existing records to determine next sequence number
        if file_path.exists():
            with open(file_path, 'r') as f:
                records = json.load(f)
                # Filter records from today
                today_records = [r for r in records if date_str in r.get('id', '')]
                sequence = len(today_records) + 1
        else:
            sequence = 1
        
        return f"{prefix}-{date_str}-{sequence:04d}"
        
    except Exception as e:
        logger.error(f"Error generating ID: {e}")
        from datetime import datetime
        return f"ERR-{datetime.now().strftime('%Y%m%d')}-0000"


def save_action_data(action_type: str, action_data: dict):
    """Save action data to appropriate JSON file"""
    try:
        from pathlib import Path
        import json

        # Determine file path
        if action_type == "initiate_refund":
            file_path = Path(__file__).parent / "data" / "refunds.json"
        elif action_type == "initiate_replacement":
            file_path = Path(__file__).parent / "data" / "replacements.json"
        elif action_type == "book_service":
            file_path = Path(__file__).parent / "data" / "service_bookings.json"
        else:
            logger.error(f"Unknown action type: {action_type}")
            return False
        
        # Read existing data
        if file_path.exists():
            with open(file_path, 'r') as f:
                records = json.load(f)
        else:
            records = []
        
        # Append new record
        records.append(action_data)
        
        # Write back to file
        with open(file_path, 'w') as f:
            json.dump(records, f, indent=2)
        
        logger.info(f"Action data saved to {file_path.name}")
        return True
        
    except Exception as e:
        logger.error(f"ERROR: Failed to save action data: {e}")
        return False


def execute_action(action: str, user_details: dict = None):
    """Execute the determined action with data persistence"""
    try:
        from datetime import datetime

        logger.info(f"Executing action: {action}")
        
        if action == "none":
            return None
        
        # Generate unique ID
        action_id = generate_action_id(action)
        
        # Prepare action data based on type
        if action == "initiate_refund":
            action_data = {
                "id": action_id,
                "refund_id": action_id,
                "product_name": user_details.get("product_name", "N/A") if user_details else "N/A",
                "user_email": user_details.get("email", "") if user_details else "",
                "user_name": user_details.get("name", "") if user_details else "",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "processing"
            }
            
        elif action == "initiate_replacement":
            action_data = {
                "id": action_id,
                "replacement_id": action_id,
                "product_name": user_details.get("product_name", "N/A") if user_details else "N/A",
                "user_email": user_details.get("email", "") if user_details else "",
                "user_name": user_details.get("name", "") if user_details else "",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "processing"
            }
            
        elif action == "book_service":
            action_data = {
                "id": action_id,
                "service_id": action_id,
                "product_name": user_details.get("product_name", "N/A") if user_details else "N/A",
                "user_email": user_details.get("email", "") if user_details else "",
                "user_name": user_details.get("name", "") if user_details else "",
                "user_address": user_details.get("address", "") if user_details else "",
                "contact_number": user_details.get("phone", "") if user_details else "",
                "service_center": user_details.get("service_center", "Nearest Center") if user_details else "Nearest Center",
                "scheduled_date": user_details.get("scheduled_date", "TBD") if user_details else "TBD",
                "time_slot": user_details.get("time_slot", "TBD") if user_details else "TBD",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            logger.warning(f"Unknown action type: {action}")
            return {
                "action": action,
                "status": "unknown",
                "message": f"Unknown action type: {action}"
            }
        
        # Save data to appropriate JSON file
        save_success = save_action_data(action, action_data)
        
        # Prepare result
        result = {
            "action": action,
            "action_id": action_id,
            "status": "success" if save_success else "partial",
            "message": f"Action '{action}' has been logged with ID: {action_id}",
            "data": action_data
        }
        
        logger.info(f"Action executed: {action_id}")
        return result
        
    except Exception as e:
        logger.error(f"ERROR: Action execution error: {e}")
        return {
            "action": action,
            "status": "failed",
            "error": str(e)
        }
