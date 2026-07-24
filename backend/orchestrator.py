"""
AURA Backend — Orchestrator

Purpose:
    The central brain of the chat system. Routes every user message
    through the various agents, manages session state, and executes actions.

Responsibilities:
    - Load user session (previous chat history, known order info)
    - Pass message to Intent Agent
    - Retrieve documents via RAG (if needed)
    - Enforce business policies (e.g. 30-day refund window)
    - Pass context to Responder Agent (LLM)
    - Trigger operational actions and send emails
    - Save conversation history to Supabase

Workflow:
    ┌─────────────────────────────────────────────────────┐
    │  User Message: "My TV screen is cracked"            │
    │      │                                              │
    │      ▼                                              │
    │  Session Manager (loads past context & order ID)    │
    │      │                                              │
    │      ▼                                              │
    │  Intent Agent  →  "replacement"                     │
    │      │                                              │
    │      ▼                                              │
    │  Retrieval Agent (RAG)  → fetches replacement policy│
    │      │                                              │
    │      ▼                                              │
    │  Policy Enforcement → checks 30-day return window   │
    │      │                                              │
    │      ▼                                              │
    │  Responder Agent (LLM) → drafts response            │
    │      │                                              │
    │      ▼                                              │
    │  Action Agent → decides to execute replacement      │
    │      │                                              │
    │      ▼                                              │
    │  Execute Action & Send Email                        │
    └─────────────────────────────────────────────────────┘

    Why this pipeline?
        Instead of one massive LLM call trying to do everything (slow,
        prone to hallucinations), we break it into deterministic steps.
        Only the Responder step uses the LLM, keeping the system fast
        and predictable.

Used By:
    main.py (/chat endpoint)

Depends On:
    agents.py, rag.py, session_manager.py, order_lookup.py, notifications.py
"""


import time
import logging
from .agents import (
    intent_agent,
    retrieval_agent,
    responder_agent,
    verifier_agent,
    action_agent,
    action_confirmation_agent,
    execute_action,
    should_use_rag,
)
from .rag import search_knowledge_with_metadata
from . import notifications
from . import session_manager
from . import order_lookup

logger = logging.getLogger(__name__)


def process_message(message: str, session_id: str = None, user: dict = None) -> dict:
    """Process user message through the AURA agent pipeline with session memory.

    Flow: Session → Order Lookup → Intent (deterministic) → RAG (conditional)
          → Responder (1 LLM call) → Action → Execution → Notification
    """
    try:
        request_start = time.time()

        # Generate session_id if not provided
        if not session_id:
            import uuid
            session_id = f"session_{uuid.uuid4().hex[:12]}"

        # Get or create session
        session = session_manager.get_session(session_id, user)

        # Add user message to conversation history
        session_manager.add_to_conversation_history(session_id, "user", message, user)

        # Check for order_id in message
        extracted_order_id = order_lookup.extract_order_id_from_message(message)
        if extracted_order_id:
            order_data = order_lookup.get_order_by_id(extracted_order_id)
            if order_data:
                session_manager.update_session_bulk(session_id, {
                    "order_id": order_data.get("id"),
                    "customer_name": order_data.get("customer_name"),
                    "customer_email": order_data.get("customer_email"),
                    "customer_phone": order_data.get("customer_phone"),
                    "product_id": order_data.get("product_id"),
                    "product_name": order_data.get("product_name"),
                    "serial_number": order_data.get("serial_number"),
                    "purchase_date": order_data.get("purchase_date"),
                    "warranty_years": order_data.get("warranty_years"),
                    "status": order_data.get("status")
                })

        # Extract reason or datetime from message (if Order ID already exists)
        if session.get("order_id") and not session.get("reason_for_action"):
            if len(message) > 10 and not message.strip().endswith("?"):
                session_manager.update_session(session_id, "reason_for_action", message.strip())

        if session.get("order_id") and not session.get("preferred_datetime"):
            datetime_keywords = ["tomorrow", "monday", "tuesday", "wednesday", "thursday",
                                 "friday", "saturday", "sunday", "next week", "pm", "am",
                                 "december", "january"]
            if any(keyword in message.lower() for keyword in datetime_keywords):
                session_manager.update_session(session_id, "preferred_datetime", message.strip())

        # Get session context for agents
        session_context = session_manager.get_session_context(session_id)

        # ── 1. Intent (DETERMINISTIC — no LLM call) ──
        intent = intent_agent(message)

        # Inherit intent if we have a pending action and the user didn't explicitly change topics
        pending_action = session.get("pending_action")
        if pending_action and intent == "general_query":
            action_to_intent = {
                "initiate_refund": "refund",
                "initiate_replacement": "replacement",
                "book_service": "service_booking"
            }
            if pending_action in action_to_intent:
                intent = action_to_intent[pending_action]
                logger.info(f"Inherited intent from pending action: {intent}")

        # ── 2. RAG Retrieval (CONDITIONAL — skipped for greetings) ──
        context = ""
        sources_metadata = []
        use_rag = should_use_rag(message, intent)

        search_ms = 0
        llm_ms = 0

        search_start = time.time()
        if use_rag:
            try:
                # Single consolidated search (was previously two separate calls)
                sources_metadata = search_knowledge_with_metadata(message, k=5)
                context = "\n\n".join(src["text"] for src in sources_metadata) if sources_metadata else ""

                # ── PHASE 1 DIAGNOSTIC: Retrieval transparency logging ──
                logger.info("=" * 80)
                logger.info(f"QUERY: {message}")
                logger.info(f"RESULTS: {len(sources_metadata)} chunks retrieved")
                for i, src in enumerate(sources_metadata):
                    logger.info(f"\n--- Chunk {i + 1} ---")
                    logger.info(f"  Source: {src.get('source', 'unknown')}")
                    logger.info(f"  Page: {src.get('page', '?')}")
                    logger.info(f"  Distance: {src.get('distance', 'N/A')}")
                    logger.info(f"  Rerank Score: {src.get('rerank_score', 'N/A')}")
                    logger.info(f"  Text: {src.get('text', '')[:600]}")
                logger.info("=" * 80)
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
        search_ms = (time.time() - search_start) * 1000

        # ── 2b. Policy Injection ──
        # Inject policies for related intents so the LLM can answer general questions
        if intent in ["refund", "replacement", "warranty", "general_query"]:
            from . import supabase_client
            policies = supabase_client.get_policies()
            if policies:
                policy_texts = []
                for p in policies:
                    ptype = p.get('policy_type', '').capitalize()
                    scope = p.get('scope', 'global')
                    cat = p.get('category')
                    desc = p.get('description', '')
                    label = f"[{ptype} Policy - {scope.capitalize()}{' ('+cat+')' if cat else ''}]"
                    policy_texts.append(f"{label}\n{desc}")
                
                if policy_texts:
                    policy_block = "\n\n--- COMPANY POLICIES ---\n" + "\n\n".join(policy_texts)
                    context = (context + policy_block).strip()

        # ── DETERMINISTIC FLOW CONTROLLER ──
        # Bypass LLM if we have complete order info and an action intent
        should_skip_to_action = False

        if session.get("order_id") and intent in ["refund", "replacement", "service_booking"]:
            from . import supabase_client
            from datetime import datetime
            
            customer_name = session.get("customer_name", "Customer")
            product_name = session.get("product_name", "your product")
            order_id = session.get("order_id")
            purchase_date = session.get("purchase_date")
            product_id = session.get("product_id")

            # ── NEW: Deterministic Policy Enforcement ──
            policy_rejected_msg = None
            if intent in ["refund", "replacement"] and purchase_date:
                # 1. Fetch product to get category
                product_data = supabase_client.get_product_by_id(product_id) if product_id else None
                category = product_data.get("category", "") if product_data else ""
                
                # 2. Resolve policy
                policy = supabase_client.resolve_policy(category, intent)
                
                # 3. Enforce window_days rule
                if policy and policy.get("rules"):
                    window_days = policy["rules"].get("window_days")
                    if window_days is not None:
                        try:
                            # Handle ISO format dates which might only have YYYY-MM-DD
                            date_str = purchase_date.split("T")[0]
                            p_date = datetime.strptime(date_str, "%Y-%m-%d")
                            days_since = (datetime.now() - p_date).days
                            if days_since > window_days:
                                # Reject!
                                action_label = "refund" if intent == "refund" else "replacement"
                                policy_rejected_msg = (
                                    f"I apologize, {customer_name}, but I cannot process a {action_label} for "
                                    f"{product_name}. Our policy for this item allows {action_label}s within "
                                    f"{window_days} days of purchase, and this order is {days_since} days old."
                                )
                        except Exception as e:
                            logger.error(f"Error parsing date for policy check: {e}")

            if policy_rejected_msg:
                # Bypass to a rejection response without triggering action
                should_skip_to_action = False
                verified_response = policy_rejected_msg
                # Reset intent so action agent doesn't trigger
                intent = "general_query"
            else:
                should_skip_to_action = True
                action_labels = {
                    "refund": "refund",
                    "replacement": "replacement",
                    "service_booking": "service appointment"
                }
                action_label = action_labels.get(intent, "request")

                verified_response = (
                    f"Thank you, {customer_name}. I understand you'd like to proceed with "
                    f"a {action_label} for {product_name} (Order ID: {order_id}).\n\n"
                    f"I'm processing your {action_label} request now. Please wait a moment..."
                )

        else:
            # ── 3. Responder (THE ONLY LLM CALL) ──
            llm_start = time.time()
            try:
                draft_response = responder_agent(context, message, session_context)
            except Exception as e:
                logger.error(f"Responder failed: {e}")
                draft_response = "I apologize, but I'm experiencing technical difficulties. Please try again later."
            llm_ms = (time.time() - llm_start) * 1000

            # ── 4. Verifier (DISABLED by default) ──
            try:
                verified_response = verifier_agent(draft_response, context)
            except Exception as e:
                logger.error(f"Verifier failed: {e}")
                verified_response = draft_response

        # ── 5. Action Agent (DETERMINISTIC) ──
        action = action_agent(intent, verified_response)

        # ── 6. Action Confirmation (TEMPLATE — no LLM) ──
        confirmation_message = None
        if action != "none":
            confirmation_message = action_confirmation_agent(action)

        # ── 7. Action Execution ──
        action_result = None

        if action != "none":
            # Save pending action in session so we don't forget it on the next turn
            session_manager.update_session(session_id, "pending_action", action)
            
            try:
                info_status = session_manager.check_missing_info_for_action(session_id, action)

                if not info_status["complete"]:
                    # Append the prompt instead of completely overwriting the LLM's answer
                    # This ensures policy questions (e.g., "what's your refund policy?") still get answered
                    if verified_response and len(message) > 10 and "?" in message:
                        verified_response = f"{verified_response}\n\n{info_status['prompt']}"
                    else:
                        verified_response = info_status["prompt"]
                    action = "none"
                else:
                    # Clear pending action because we have all info and are executing it now
                    session_manager.update_session(session_id, "pending_action", None)
                    
                    user_details = {
                        "email": session.get("customer_email") or (user.get("email") if user else None),
                        "name": session.get("customer_name"),
                        "product_name": session.get("product_name"),
                        "order_id": session.get("order_id"),
                        "phone": session.get("customer_phone") or "",
                        "scheduled_date": session.get("preferred_datetime", "TBD"),
                        "time_slot": "As requested" if session.get("preferred_datetime") else "TBD"
                    }

                    action_result = execute_action(action, user_details)

                    if action_result and action_result.get("status") == "success":
                        action_id = action_result.get("action_id")

                        action_labels = {
                            "initiate_refund": "refund",
                            "initiate_replacement": "replacement",
                            "book_service": "service appointment"
                        }
                        action_label = action_labels.get(action, "request")

                        verified_response = (
                            f"Your {action_label} request has been processed.\n\n"
                            f"**Request ID:** {action_id}\n\n"
                            f"You'll receive confirmation via email shortly."
                        )

                        # Send email notification in background
                        user_email = user_details.get("email")
                        product_name = user_details.get("product_name", "Your Product")

                        try:
                            if action == "initiate_refund":
                                notifications.send_refund_confirmation_email(action_id, product_name, user_email)
                            elif action == "initiate_replacement":
                                notifications.send_replacement_confirmation_email(action_id, product_name, user_email)
                            elif action == "book_service":
                                booking_details = action_result.get("data", {})
                                notifications.send_service_booking_confirmation_email(action_id, booking_details, user_email)
                        except Exception as e:
                            logger.error(f"Email notification failed: {e}")

                        session_manager.mark_action_completed(session_id, action_id, action)

            except Exception as e:
                logger.error(f"Action execution failed: {e}", exc_info=True)
                action_result = {"status": "failed", "error": str(e)}
                verified_response += "\n\nI apologize, but I encountered an error processing your request. Please try again or contact support directly."

        # Build source citations for the UI
        citations = [
            {
                "source": src.get("source", "unknown"),
                "page": src.get("page", 0),
                "chunk_index": src.get("chunk_index", 0),
            }
            for src in sources_metadata
        ]

        # Persist assistant response
        session_manager.add_to_conversation_history(session_id, "assistant", verified_response, user, citations)

        # ── Structured request log ──
        total_ms = (time.time() - request_start) * 1000
        logger.info(
            f"[PERF] session={session_id[:20]} intent={intent} rag={'yes' if use_rag else 'skip'} "
            f"search_ms={search_ms:.0f} llm_ms={llm_ms:.0f} total_ms={total_ms:.0f}"
        )

        return {
            "answer": verified_response,
            "intent": intent,
            "rag_sources": context[:500],
            "sources": citations,
            "action": action,
            "action_confirmation": confirmation_message,
            "action_log": action_result,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"Critical error in process_message: {e}", exc_info=True)
        return {
            "answer": "I apologize, but I encountered an error processing your request. Please try again.",
            "intent": "error",
            "rag_sources": "",
            "sources": [],
            "action": "none",
            "action_confirmation": None,
            "action_log": None,
            "session_id": session_id if session_id else "unknown"
        }
