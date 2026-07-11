"""
AURA Agents — Intent, Retrieval, Responder, Verifier, Action, Execution.

OPTIMIZED:
- Intent classification is now DETERMINISTIC (regex/keyword, no LLM call).
- Verifier is disabled by default (ENABLE_VERIFIER=false).
- Action confirmation uses predefined templates (no LLM call).
- `should_use_rag()` helper skips RAG for greetings/short replies.
- Net result: 1 LLM call per message (responder only), down from 3–4.
"""

import os
import re
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .llm_client import get_completion
from .rag import search_knowledge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────
ENABLE_VERIFIER = os.getenv("ENABLE_VERIFIER", "false").lower() == "true"


# ────────────────────────── RAG SKIP LOGIC ─────────────────────────

# Messages that should NOT trigger RAG retrieval
_SKIP_RAG_EXACT = frozenset({
    "hi", "hello", "hey", "hii", "hiii", "helo", "hola",
    "thanks", "thank you", "thankyou", "thx", "ty",
    "bye", "goodbye", "good bye", "see you",
    "yes", "no", "yeah", "yep", "nope", "nah",
    "okay", "ok", "sure", "great", "good", "fine",
    "cool", "awesome", "got it", "alright", "right",
    "hmm", "oh", "ah", "wow",
})

# Intents that DO need RAG
_RAG_INTENTS = frozenset({
    "troubleshoot", "product_information", "refund",
    "replacement", "service_booking", "order_status",
})


def should_use_rag(message: str, intent: str) -> bool:
    """Decide whether RAG retrieval is needed for this message.

    Skip RAG for greetings, short acknowledgments, and conversational filler.
    Run RAG for troubleshooting, product questions, policies, etc.
    """
    normalized = message.strip().lower().rstrip("!?.,")

    # Exact match against skip list
    if normalized in _SKIP_RAG_EXACT:
        return False

    # Very short messages are unlikely to be knowledge queries
    if len(normalized) < 4:
        return False

    # Intent-based decision
    if intent in _RAG_INTENTS:
        return True

    # For general_query, use RAG if message is long enough to be a real question
    if intent == "general_query" and len(normalized) > 15:
        return True

    return False


# ────────────────────────── INTENT AGENT ──────────────────────────

# Keyword → intent mapping (checked in order, first match wins)
_INTENT_RULES = [
    # Refund
    (r"\b(refund|money\s*back|return\s*(?:the|my|this)?(?:\s+\w+)?\s*(?:product|item|order)?)\b", "refund"),
    # Replacement
    (r"\b(replac(?:e|ement)|swap|exchange|defective|broken|damaged|not\s*working)\b", "replacement"),
    # Service booking
    (r"\b(book\s*(?:a\s*)?service|service\s*(?:appointment|booking|visit|request)|schedule\s*(?:a\s*)?(?:service|repair|visit)|technician|repair)\b", "service_booking"),
    # Order status
    (r"\b(order\s*(?:status|track|where)|track\s*(?:my\s*)?order|where\s*(?:is|'s)\s*(?:my\s*)?order|delivery\s*status|shipping\s*status)\b", "order_status"),
    # Troubleshoot
    (r"\b(troubleshoot|fix|issue|problem|error|not\s*(?:working|turning|heating|cooling|spinning|starting)|doesn'?t\s*work|won'?t\s*(?:turn|start|work)|how\s*(?:to|do\s*i)\s*(?:fix|solve|resolve))\b", "troubleshoot"),
    # Product information
    (r"\b(how\s*(?:to|do\s*i)\s*(?:install|setup|set\s*up|use|clean|operate|maintain)|install(?:ation)?|setup|set\s*up|manual|guide|specification|feature|warranty|what\s*(?:is|are)\s*(?:the\s*)?(?:feature|spec))\b", "product_information"),
]


def intent_agent(user_message: str) -> str:
    """Classify user intent — DETERMINISTIC (no LLM call).

    Uses regex/keyword rules. Falls back to 'general_query' if no match.
    """
    try:
        msg_lower = user_message.strip().lower()

        for pattern, intent in _INTENT_RULES:
            if re.search(pattern, msg_lower):
                logger.info(f"Intent classified (deterministic): {intent}")
                return intent

        logger.info("Intent classified (deterministic): general_query")
        return "general_query"

    except Exception as e:
        logger.error(f"Intent agent error: {e}")
        return "general_query"


# ────────────────────── RETRIEVAL AGENT ───────────────────────────

def retrieval_agent(query: str) -> str:
    """Retrieve relevant context from the knowledge base."""
    try:
        docs = search_knowledge(query)
        context = "\n\n".join(docs) if docs else ""
        logger.info(f"Retrieved {len(docs)} documents")
        return context
    except Exception as e:
        logger.error(f"Retrieval agent error: {e}")
        return ""


# ────────────────────── RESPONDER AGENT ───────────────────────────

def responder_agent(context: str, message: str, session_context: str = "") -> str:
    """Generate the main human-like reply using retrieved context."""
    try:
        system_prompt = (
            "You are AURA, a professional and empathetic customer support executive.\n\n"
            "Your job is to answer the user accurately using ONLY the provided context.\n"
            "If the context is insufficient, clearly state what additional information is required.\n\n"
            "CRITICAL RULES:\n"
            "- Be clear, polite, and professional.\n"
            "- Respond in the SAME language as the user.\n"
            "- Provide step-by-step guidance if troubleshooting.\n"
            "- Do not invent facts, policies, or procedures.\n"
            "- DO NOT ask for information already mentioned in 'Known Information' above.\n"
            "- Only ask for information that is truly missing and required.\n\n"
            "CITATION RULES:\n"
            "- Reference the source document name and page number for each key claim "
            "(e.g., 'According to the LG Washing Machine Manual, page 12, ...').\n"
            "- If multiple sources support different parts of your answer, cite each separately.\n\n"
            "PARTIAL MATCH HANDLING:\n"
            "- If the context partially answers the question, answer the part you can and "
            "clearly state what information is missing or not covered.\n"
            "- Do NOT refuse to answer entirely just because one aspect is missing.\n\n"
            "EXAMPLES:\n\n"
            "Good grounded answer:\n"
            "User: 'How do I clean the filter?'\n"
            "Response: 'According to the Product Manual (page 15), you can clean the filter by: "
            "1. Turn off the device and unplug it. 2. Open the filter access panel on the bottom right. "
            "3. Place a towel underneath to catch water. 4. Twist the filter cap counterclockwise and remove it. "
            "5. Rinse the filter under running water. 6. Replace and secure the cap.'\n\n"
            "Good insufficient-context refusal:\n"
            "User: 'What is the error code E5 on my XYZ model?'\n"
            "Response: 'I don't have specific information about error code E5 for your model in my "
            "current knowledge base. I'd recommend checking the troubleshooting section of your product "
            "manual or contacting our technical support team for model-specific error codes.'"
        )

        user_content = ""
        if session_context:
            user_content += f"{session_context}\n\n"
        user_content += f"Context:\n{context if context else 'No context available'}\n\n"
        user_content += f"User query:\n{message}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = get_completion(messages, temperature=0.3, max_tokens=1024)
        response_text = resp.strip()
        logger.info(f"Response generated ({len(response_text)} chars)")
        return response_text

    except Exception as e:
        logger.error(f"Responder agent error: {e}")
        return "I apologize, but I'm having trouble processing your request. Please try again."


# ────────────────────── VERIFIER AGENT ────────────────────────────

def verifier_agent(draft_response: str, context: str = "") -> str:
    """Verify draft response quality and accuracy.

    DISABLED by default (ENABLE_VERIFIER=false).
    Returns draft as-is if verification is disabled or fails.
    """
    if not ENABLE_VERIFIER:
        return draft_response

    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a response quality and accuracy verifier for a customer support system.\n\n"
                    "Your job is to check the draft response against the provided context chunks and either:\n"
                    "- Return it unchanged if it's accurate and well-grounded\n"
                    "- Return a corrected version if it needs fixes\n"
                    "- Return a REJECTION with regeneration guidance if there are serious issues\n\n"
                    "HALLUCINATION CHECK (CRITICAL):\n"
                    "- Compare every factual claim in the draft against the provided context.\n"
                    "- If the draft contains information NOT present in the context chunks, "
                    "REMOVE that information and note it was unsupported.\n"
                    "- Pay special attention to: specific numbers, dates, model numbers, "
                    "procedure steps, policy details, and error codes.\n\n"
                    "CITATION CHECK:\n"
                    "- Verify that source references in the draft (document names, page numbers) "
                    "match the actual context provided.\n"
                    "- Fix any incorrect citations.\n\n"
                    "COMPLETENESS CHECK:\n"
                    "- If the context contains relevant information that the draft missed, "
                    "add it to the response.\n\n"
                    "OUTPUT RULES:\n"
                    "- Only output the final response text (no meta-commentary or explanations).\n"
                    "- Keep the tone professional and friendly.\n"
                    "- Preserve the original language of the draft."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Retrieved Context Chunks:\n{context}\n\n"
                    f"Draft Response to Verify:\n{draft_response}"
                ),
            },
        ]

        resp = get_completion(messages, temperature=0.1, max_tokens=1024)
        verified = resp.strip()
        logger.info("Response verified via LLM (hallucination + citation check)")
        return verified

    except Exception as e:
        logger.error(f"Verifier agent error: {e}")
        return draft_response  # graceful fallback


# ────────────────────── ACTION AGENT ──────────────────────────────

def action_agent(intent: str, verified_response: str) -> str:
    """Decide whether a real operational action is required.

    DETERMINISTIC: Maps intent directly to action (no LLM needed).
    """
    try:
        intent_to_action = {
            "refund": "initiate_refund",
            "replacement": "initiate_replacement",
            "service_booking": "book_service",
            "order_status": "none",
            "product_information": "none",
            "troubleshoot": "none",
            "general_query": "none",
        }

        action = intent_to_action.get(intent, "none")
        logger.info(f"Action decided (deterministic): {action}")
        return action

    except Exception as e:
        logger.error(f"Action agent error: {e}")
        return "none"


# ──────────────── ACTION CONFIRMATION AGENT ───────────────────────

# Predefined confirmation templates (no LLM call)
_CONFIRMATION_TEMPLATES = {
    "initiate_refund": (
        "I'd like to process a refund for you. "
        "Once initiated, the refund will be reviewed and processed within 3–5 business days. "
        "Shall I proceed?"
    ),
    "initiate_replacement": (
        "I'll initiate a replacement request for your product. "
        "Our team will arrange pickup of the defective unit and dispatch a replacement. "
        "Shall I proceed?"
    ),
    "book_service": (
        "I'll book a service appointment for you. "
        "A technician will be assigned and you'll receive confirmation details shortly. "
        "Shall I proceed?"
    ),
}


def action_confirmation_agent(action_type: str) -> Optional[str]:
    """Return a confirmation message for the action.

    Uses predefined templates instead of an LLM call.
    """
    try:
        if action_type == "none":
            return None

        message = _CONFIRMATION_TEMPLATES.get(action_type)
        if message:
            logger.info(f"Confirmation message (template): {action_type}")
            return message

        # Fallback for unknown action types
        return f"To proceed with {action_type}, please confirm."

    except Exception as e:
        logger.error(f"Action confirmation error: {e}")
        return f"To proceed with {action_type}, please confirm."


# ──────────────── ACTION EXECUTION (unchanged) ────────────────────

def generate_action_id(action_type: str) -> str:
    """Generate unique action ID in format: REF-YYYYMMDD-XXXX."""
    try:
        date_str = datetime.now().strftime("%Y%m%d")

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

        if file_path.exists():
            with open(file_path, "r") as f:
                records = json.load(f)
                today_records = [r for r in records if date_str in r.get("id", "")]
                sequence = len(today_records) + 1
        else:
            sequence = 1

        return f"{prefix}-{date_str}-{sequence:04d}"

    except Exception as e:
        logger.error(f"Error generating ID: {e}")
        return f"ERR-{datetime.now().strftime('%Y%m%d')}-0000"


def save_action_data(action_type: str, action_data: dict):
    """Save action data to appropriate JSON file."""
    try:
        if action_type == "initiate_refund":
            file_path = Path(__file__).parent / "data" / "refunds.json"
        elif action_type == "initiate_replacement":
            file_path = Path(__file__).parent / "data" / "replacements.json"
        elif action_type == "book_service":
            file_path = Path(__file__).parent / "data" / "service_bookings.json"
        else:
            logger.error(f"Unknown action type: {action_type}")
            return False

        if file_path.exists():
            with open(file_path, "r") as f:
                records = json.load(f)
        else:
            records = []

        records.append(action_data)

        with open(file_path, "w") as f:
            json.dump(records, f, indent=2)

        logger.info(f"Action data saved to {file_path.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to save action data: {e}")
        return False


def execute_action(action: str, user_details: dict = None):
    """Execute the determined action with data persistence."""
    try:
        logger.info(f"Executing action: {action}")

        if action == "none":
            return None

        action_id = generate_action_id(action)

        if action == "initiate_refund":
            action_data = {
                "id": action_id,
                "refund_id": action_id,
                "product_name": user_details.get("product_name", "N/A") if user_details else "N/A",
                "user_email": user_details.get("email", "") if user_details else "",
                "user_name": user_details.get("name", "") if user_details else "",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "processing",
            }

        elif action == "initiate_replacement":
            action_data = {
                "id": action_id,
                "replacement_id": action_id,
                "product_name": user_details.get("product_name", "N/A") if user_details else "N/A",
                "user_email": user_details.get("email", "") if user_details else "",
                "user_name": user_details.get("name", "") if user_details else "",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "processing",
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
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        else:
            logger.warning(f"Unknown action type: {action}")
            return {
                "action": action,
                "status": "unknown",
                "message": f"Unknown action type: {action}",
            }

        save_success = save_action_data(action, action_data)

        result = {
            "action": action,
            "action_id": action_id,
            "status": "success" if save_success else "partial",
            "message": f"Action '{action}' has been logged with ID: {action_id}",
            "data": action_data,
        }

        logger.info(f"Action executed: {action_id}")
        return result

    except Exception as e:
        logger.error(f"Action execution error: {e}")
        return {"action": action, "status": "failed", "error": str(e)}
