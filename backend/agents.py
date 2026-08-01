"""
AURA Backend — Agents

Purpose:
    Specialized "agents" that each handle one step of the chat pipeline.
    Together they form a multi-agent architecture where each agent has
    a single, well-defined responsibility.

Responsibilities:
    - Classify user intent (deterministic, no LLM)
    - Retrieve documents from the knowledge base
    - Generate human-like responses using LLM + retrieved context
    - Verify responses for hallucinations (optional)
    - Decide and execute operational actions (refund, replacement, service)

Agent Pipeline:
    ┌─────────────────────────────────────────────────────┐
    │  User Message                                       │
    │      │                                              │
    │      ▼                                              │
    │  Intent Agent  (deterministic regex — no LLM)       │
    │      │                                              │
    │      ▼                                              │
    │  should_use_rag()  →  skip for greetings/short msgs │
    │      │                                              │
    │      ▼                                              │
    │  Retrieval Agent  →  ChromaDB + BM25 hybrid search  │
    │      │                                              │
    │      ▼                                              │
    │  Responder Agent  →  LLM generates answer from      │
    │      │                 retrieved context             │
    │      ▼                                              │
    │  Verifier Agent   →  (optional) checks for          │
    │      │                 hallucinations                │
    │      ▼                                              │
    │  Action Agent     →  decides: refund? replacement?   │
    │      │                 service booking? or none?     │
    │      ▼                                              │
    │  Execute Action   →  save record + send email       │
    └─────────────────────────────────────────────────────┘

    Performance:
        Intent + Action agents are deterministic (regex/dict lookup).
        Only the Responder uses an LLM call.
        Verifier is disabled by default.
        Net result: ~1 LLM call per message.

Used By:
    orchestrator.py  (calls agents in sequence)

Depends On:
    llm_client.py  — get_completion()
    rag.py         — search_knowledge()

Related Files:
    orchestrator.py  — orchestrates the agent pipeline
    llm_client.py    — LLM API gateway
    rag.py           — vector + keyword retrieval
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


# ==========================================================
# CONFIGURATION
# ==========================================================
ENABLE_VERIFIER = os.getenv("ENABLE_VERIFIER", "false").lower() == "true"


# ==========================================================
# RAG SKIP LOGIC
# ==========================================================
# Why skip RAG for some messages?
# Greetings like "hi" or "thanks" don't need a knowledge base search.
# Skipping RAG for these saves an embedding computation + ChromaDB
# query, making the response ~500ms faster.

_SKIP_RAG_EXACT = frozenset({
    "hi", "hello", "hey", "hii", "hiii", "helo", "hola",
    "thanks", "thank you", "thankyou", "thx", "ty",
    "bye", "goodbye", "good bye", "see you",
    "yes", "no", "yeah", "yep", "nope", "nah",
    "okay", "ok", "sure", "great", "good", "fine",
    "cool", "awesome", "got it", "alright", "right",
    "hmm", "oh", "ah", "wow",
})

# Intents that DO need RAG (they require document evidence)
_RAG_INTENTS = frozenset({
    "troubleshoot", "product_information", "refund",
    "replacement", "service_booking", "order_status",
})


def should_use_rag(message: str, intent: str) -> bool:
    """Decide whether RAG retrieval is needed for this message."""
    normalized = message.strip().lower().rstrip("!?.,")

    if normalized in _SKIP_RAG_EXACT:
        return False

    if len(normalized) < 4:
        return False

    if intent in _RAG_INTENTS:
        return True

    # For general_query, use RAG if message is long enough to be a real question
    if intent == "general_query" and len(normalized) > 15:
        return True

    return False


# ==========================================================
# INTENT AGENT
#
# Role:
#     Classify what the user wants (refund, troubleshoot, etc.)
#
# Why deterministic (no LLM)?
#     Calling the LLM just to classify intent wastes ~300ms and
#     a rate-limited API call.  Regex patterns are instant, free,
#     and equally accurate for our use cases.
#
# Input:  User message (str)
# Output: Intent label (str) — e.g. "refund", "troubleshoot"
# ==========================================================

# Keyword → intent mapping (checked in order, first match wins)
_INTENT_RULES = [
    # Refund
    (r"\b(refund|money\s*back|return\s*(?:the|my|this)?(?:\s+\w+)?\s*(?:product|item|order)?)\b", "refund"),
    # Replacement
    (r"\b(replac(?:e|ement)|swap|exchange|defective|broken|damaged|not\s*working)\b", "replacement"),
    # Service booking
    (r"\b(book\s*(?:a\s*)?(?:service|serivce)|(?:service|serivce)\s*(?:appointment|booking|visit|request)|schedule\s*(?:a\s*)?(?:service|serivce|repair|visit)|technician|repair)\b", "service_booking"),
    # Order status
    (r"\b(order\s*(?:status|track|where)|track\s*(?:my\s*)?order|where\s*(?:is|'s)\s*(?:my\s*)?order|delivery\s*status|shipping\s*status)\b", "order_status"),
    # Troubleshoot
    (r"\b(troubleshoot|fix|issue|problem|error|not\s*(?:working|turning|heating|cooling|spinning|starting)|doesn'?t\s*work|won'?t\s*(?:turn|start|work)|how\s*(?:to|do\s*i)\s*(?:fix|solve|resolve))\b", "troubleshoot"),
    # Product information
    (r"\b(how\s*(?:to|do\s*i)\s*(?:install|setup|set\s*up|use|clean|operate|maintain)|install(?:ation)?|setup|set\s*up|manual|guide|specification|feature|warranty|what\s*(?:is|are)\s*(?:the\s*)?(?:feature|spec))\b", "product_information"),
]


def intent_agent(user_message: str) -> str:
    """Classify user intent using deterministic regex rules."""
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


# ==========================================================
# RETRIEVAL AGENT
#
# Role:
#     Find relevant documents from the knowledge base.
#
# Why needed?
#     The LLM has no memory of company documents (manuals, policies).
#     We must search the knowledge base first and pass the results
#     as context so the LLM can give evidence-based answers.
#     This prevents hallucinations.
#
# Input:  User query (str)
# Output: Retrieved document text (str)
# Used By: orchestrator.py
# ==========================================================

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


# ==========================================================
# RESPONDER AGENT
#
# Role:
#     Generate the final human-like reply using LLM + context.
#
# Why not just call the LLM directly?
#     The raw LLM would hallucinate (make up answers).
#     By injecting retrieved context into the prompt, we force
#     the LLM to answer ONLY from verified documents.
#
# Prompt Objective:  Answer accurately from provided context only.
# Temperature:       0.3 (low creativity — factual answers)
# Input:  context (retrieved docs), message (user query), session_context
# Output: Natural language response (str)
# ==========================================================

def responder_agent(context: str, message: str, session_context: str = "", conversation_history: list = None) -> str:
    """Generate the main response using retrieved context + LLM."""
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        system_prompt = (
            f"You are AURA, a professional and empathetic customer support executive. Today's date is {current_date}.\n\n"
            "Your job is to answer the user accurately using ONLY the information provided to you in the context.\n"
            "If the information is insufficient to answer the question, clearly state what additional information is required or recommend contacting support.\n\n"
            "CRITICAL RULES:\n"
            "- Be clear, polite, and professional.\n"
            "- Respond in the SAME language as the user.\n"
            "- Provide step-by-step guidance if troubleshooting.\n"
            "- Do not invent facts, policies, or procedures.\n"
            "- NEVER use phrases like 'provided context', 'search results', 'knowledge base', or 'internal data'. Speak naturally as an expert who simply knows this information.\n"
            "- DO NOT ask for information already mentioned in 'Known Information' above.\n"
            "- Only ask for information that is truly missing and required.\n\n"
            "CITATION RULES:\n"
            "- Reference the source document name and page number for each key claim "
            "(e.g., 'According to the LG Washing Machine Manual, page 12, ...').\n"
            "- If multiple sources support different parts of your answer, cite each separately.\n\n"
            "PARTIAL MATCH HANDLING:\n"
            "- If you can partially answer the question, answer the part you can and "
            "clearly state what information is missing or not covered.\n"
            "- Do NOT refuse to answer entirely just because one aspect is missing.\n\n"
            "POLICY HANDLING RULES:\n"
            "- If a 'Global' policy is provided in the context under 'COMPANY POLICIES', it applies to ALL products automatically, unless a category-specific policy overrides it.\n"
            "- If a user asks about a specific product's policy, ALWAYS use the Global policy to answer them if no specific override exists. Do NOT say you don't have information for their specific product.\n\n"
            "EXAMPLES:\n\n"
            "Good grounded answer:\n"
            "User: 'How do I clean the filter?'\n"
            "Response: 'According to the Product Manual (page 15), you can clean the filter by: "
            "1. Turn off the device and unplug it. 2. Open the filter access panel on the bottom right. "
            "3. Place a towel underneath to catch water. 4. Twist the filter cap counterclockwise and remove it. "
            "5. Rinse the filter under running water. 6. Replace and secure the cap.'\n\n"
            "Good insufficient-context refusal:\n"
            "User: 'What is the error code E5 on my XYZ model?'\n"
            "Response: 'I don't have specific information about error code E5 for your model. I'd recommend checking the troubleshooting section of your product "
            "manual or contacting our technical support team for model-specific error codes.'"
        )

        user_content = ""
        if session_context:
            user_content += f"{session_context}\n\n"
        user_content += f"Context:\n{context if context else 'No context available'}\n\n"
        user_content += f"User query:\n{message}"

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages
                role = "assistant" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "content": msg["message"]})

        messages.append({"role": "user", "content": user_content})

        resp = get_completion(messages, temperature=0.3, max_tokens=1024)
        response_text = resp.strip()
        logger.info(f"Response generated ({len(response_text)} chars)")
        return response_text

    except Exception as e:
        logger.error(f"Responder agent error: {e}")
        return "I apologize, but I'm having trouble processing your request. Please try again."


# ==========================================================
# VERIFIER AGENT
#
# Role:
#     Check the responder's draft for hallucinations and fix them.
#
# Why?
#     Even with context injection, the LLM can still hallucinate
#     details (wrong page numbers, invented procedures).  The
#     verifier cross-checks every claim against the source context.
#
# Disabled by default (ENABLE_VERIFIER=false) because:
#     - It costs an extra LLM call per message
#     - The responder prompt is already well-constrained
#     - Enable it when accuracy is critical (e.g. medical devices)
#
# Prompt Objective:  Cross-check claims against context, fix errors.
# Temperature:       0.1 (minimal creativity — strict fact-checking)
# Input:  draft_response, context
# Output: Verified/corrected response (str)
# ==========================================================

def verifier_agent(draft_response: str, context: str = "") -> str:
    """Verify draft response for hallucinations and citation accuracy."""
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


# ==========================================================
# ACTION AGENT
#
# Role:
#     Decide whether the user's intent requires an operational
#     action (refund, replacement, service booking) or just
#     an informational response.
#
# Why deterministic?
#     The mapping from intent → action is a simple lookup table.
#     No LLM reasoning is needed.
#
# Input:  intent (str)
# Output: action type (str) — e.g. "initiate_refund" or "none"
# ==========================================================

def action_agent(intent: str, verified_response: str) -> str:
    """Map intent to operational action (deterministic lookup)."""
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


# ==========================================================
# ACTION CONFIRMATION
# ==========================================================
# Why templates instead of LLM?
# Confirmation messages are always the same for each action type.
# Using templates is instant, consistent, and free.

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
    """Return a confirmation message for the given action type."""
    try:
        if action_type == "none":
            return None

        message = _CONFIRMATION_TEMPLATES.get(action_type)
        if message:
            logger.info(f"Confirmation message (template): {action_type}")
            return message

        return f"To proceed with {action_type}, please confirm."

    except Exception as e:
        logger.error(f"Action confirmation error: {e}")
        return f"To proceed with {action_type}, please confirm."


# ==========================================================
# ACTION EXECUTION
# ==========================================================

def generate_action_id(action_type: str) -> str:
    """Generate unique action ID (e.g. REF-20260724-A1B2)."""
    try:
        date_str = datetime.now().strftime("%Y%m%d")

        if action_type == "initiate_refund":
            prefix = "REF"
        elif action_type == "initiate_replacement":
            prefix = "REP"
        elif action_type == "book_service":
            prefix = "SRV"
        else:
            prefix = "ACT"

        import uuid
        sequence = uuid.uuid4().hex[:4].upper()

        return f"{prefix}-{date_str}-{sequence}"

    except Exception as e:
        logger.error(f"Error generating ID: {e}")
        return f"ERR-{datetime.now().strftime('%Y%m%d')}-0000"


def save_action_data(action_type: str, action_data: dict):
    """Persist action record to Supabase."""
    try:
        from . import supabase_client
        if action_type == "initiate_refund":
            db_data = {
                "refund_id": action_data.get("refund_id"),
                "order_id": action_data.get("order_id"),
                "product_name": action_data.get("product_name"),
                "user_email": action_data.get("user_email"),
                "user_name": action_data.get("user_name"),
                "status": action_data.get("status", "processing")
            }
            return supabase_client.insert_refund(db_data) is not None
            
        elif action_type == "initiate_replacement":
            db_data = {
                "replacement_id": action_data.get("replacement_id"),
                "order_id": action_data.get("order_id"),
                "product_name": action_data.get("product_name"),
                "user_email": action_data.get("user_email"),
                "user_name": action_data.get("user_name"),
                "status": action_data.get("status", "processing")
            }
            return supabase_client.insert_replacement(db_data) is not None
            
        elif action_type == "book_service":
            db_data = {
                "service_id": action_data.get("service_id"),
                "order_id": action_data.get("order_id"),
                "product_name": action_data.get("product_name"),
                "user_email": action_data.get("user_email"),
                "user_name": action_data.get("user_name"),
                "user_address": action_data.get("user_address"),
                "contact_number": action_data.get("contact_number"),
                "service_center": action_data.get("service_center", "Nearest Center"),
                "scheduled_date": action_data.get("scheduled_date", "TBD"),
                "time_slot": action_data.get("time_slot", "TBD")
            }
            return supabase_client.insert_service_booking(db_data) is not None
            
        else:
            logger.error(f"Unknown action type: {action_type}")
            return False

    except Exception as e:
        logger.error(f"Failed to save action data to Supabase: {e}")
        return False


def execute_action(action: str, user_details: dict = None):
    """
    Execute the determined action and persist the record.

    Called By:  orchestrator.py → process_message() (action branch)
    Calls:     generate_action_id(), save_action_data()
    Returns:   {"action": ..., "action_id": ..., "status": ..., "data": ...}
    """
    try:
        logger.info(f"Executing action: {action}")

        if action == "none":
            return None

        action_id = generate_action_id(action)

        if action == "initiate_refund":
            action_data = {
                "id": action_id,
                "refund_id": action_id,
                "order_id": user_details.get("order_id", None) if user_details else None,
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
                "order_id": user_details.get("order_id", None) if user_details else None,
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
                "order_id": user_details.get("order_id", None) if user_details else None,
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
