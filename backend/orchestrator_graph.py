"""
AURA Backend — LangGraph Orchestrator

Purpose:
    Graph-based reimplementation of the sequential pipeline in
    orchestrator.py.  Every pipeline stage is a LangGraph node
    with explicit conditional edges reproducing the exact same
    branching logic.

    This is a STRUCTURAL refactor — no logic changes.  The graph
    produces byte-identical responses to the original orchestrator.

Architecture:
    ┌────────────────────────────────────────────────────────┐
    │                  LangGraph StateGraph                  │
    │                                                        │
    │  START                                                 │
    │    │                                                   │
    │    ▼                                                   │
    │  load_session ─► classify_intent ─► should_retrieve?   │
    │                                       │           │    │
    │                                      YES          NO   │
    │                                       │           │    │
    │                                       ▼           │    │
    │                                    retrieve       │    │
    │                                       │           │    │
    │                                       ▼           ▼    │
    │                                  enforce_policy ◄──┘   │
    │                                    │         │         │
    │                                rejected   ok/skip      │
    │                                    │         │         │
    │                                    │     respond       │
    │                                    │         │         │
    │                                    │      verify       │
    │                                    │         │         │
    │                                    ▼         ▼         │
    │                                decide_action           │
    │                                    │         │         │
    │                                has_action   none       │
    │                                    │         │         │
    │                                    ▼         │         │
    │                              execute_action  │         │
    │                                    │         │         │
    │                                    ▼         ▼         │
    │                                  persist               │
    │                                    │                   │
    │                                    ▼                   │
    │                                   END                  │
    └────────────────────────────────────────────────────────┘

    MemorySaver Note:
        The checkpointer is in-memory only.  It enables resumability
        within a single process lifetime (e.g. if a node fails and the
        graph is re-invoked with the same thread_id, it resumes from the
        last checkpoint).  It does NOT survive server restarts.
        TODO: Replace with PostgresSaver backed by Supabase for
        production durability.

Used By:
    main.py — swap the import to use this instead of orchestrator.py:
        from backend.orchestrator_graph import process_message

Depends On:
    agents.py, rag.py, session_manager.py, order_lookup.py, notifications.py,
    langgraph
"""

import time
import uuid
import logging
from typing import Optional, TypedDict, List, Dict
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .agents import (
    intent_agent,
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


# ══════════════════════════════════════════════════════════════
# STATE DEFINITION
# ══════════════════════════════════════════════════════════════

class AuraState(TypedDict):
    """All data threaded through the AURA agent pipeline.

    Each field maps to a local variable that was previously passed
    between stages inside process_message()'s single-function body.
    """
    # ── Input ────────────────────────────────────────────────
    message: str
    session_id: str
    user: Optional[dict]

    # ── Session context ──────────────────────────────────────
    session: dict
    session_context: str

    # ── Pipeline outputs ─────────────────────────────────────
    intent: str
    use_rag: bool
    context: str
    sources_metadata: list
    verified_response: str
    action: str
    confirmation_message: Optional[str]
    action_result: Optional[dict]

    # ── Policy / flow control ────────────────────────────────
    policy_rejected: bool
    should_skip_to_action: bool

    # ── Timing ───────────────────────────────────────────────
    search_ms: float
    llm_ms: float
    request_start: float

    # ── Final response (assembled in persist node) ───────────
    response_dict: dict


# ══════════════════════════════════════════════════════════════
# NODE IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════

def load_session_node(state: AuraState) -> dict:
    """Session lookup + order ID extraction + reason/datetime extraction.

    Exact port of orchestrator.py lines 83–137.
    """
    message = state["message"]
    session_id = state["session_id"]
    user = state.get("user")

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
                "status": order_data.get("status"),
            })

    # Extract reason or datetime from message
    if session.get("order_id") and not session.get("reason_for_action"):
        if len(message) > 10 and not message.strip().endswith("?"):
            session_manager.update_session(
                session_id, "reason_for_action", message.strip()
            )

    if session.get("order_id") and not session.get("preferred_datetime"):
        datetime_keywords = [
            "tomorrow", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "next week", "pm", "am",
            "december", "january", "february", "march", "april", "may",
            "june", "july", "august", "september", "october", "november",
        ]
        if any(keyword in message.lower() for keyword in datetime_keywords):
            extracted_dt = message.strip()
            lower_msg = message.lower()
            if " at " in lower_msg:
                extracted_dt = message[lower_msg.rfind(" at ") + 4 :].strip()
            elif " on " in lower_msg:
                extracted_dt = message[lower_msg.rfind(" on ") + 4 :].strip()
            session_manager.update_session(
                session_id, "preferred_datetime", extracted_dt
            )

    session_context = session_manager.get_session_context(session_id)

    return {
        "session": session,
        "session_context": session_context,
    }


def classify_intent_node(state: AuraState) -> dict:
    """Deterministic intent classification — wraps intent_agent().

    Exact port of orchestrator.py lines 139–152.
    """
    message = state["message"]
    session = state["session"]

    # ── 1. Intent (DETERMINISTIC — no LLM call) ──
    intent = intent_agent(message)

    # Inherit intent if we have a pending action and the user didn't change topics
    pending_action = session.get("pending_action")
    if pending_action and intent == "general_query":
        action_to_intent = {
            "initiate_refund": "refund",
            "initiate_replacement": "replacement",
            "book_service": "service_booking",
        }
        if pending_action in action_to_intent:
            intent = action_to_intent[pending_action]
            logger.info(f"Inherited intent from pending action: {intent}")

    # Determine whether RAG retrieval is needed
    use_rag = should_use_rag(message, intent)

    return {"intent": intent, "use_rag": use_rag}


def retrieve_node(state: AuraState) -> dict:
    """RAG retrieval + policy injection — conditional node.

    Exact port of orchestrator.py lines 154–202.
    Only runs when should_use_rag() returned True.
    """
    message = state["message"]
    intent = state["intent"]

    context = ""
    sources_metadata: list = []
    search_ms = 0.0

    search_start = time.time()
    try:
        sources_metadata = search_knowledge_with_metadata(message, k=5)
        context = (
            "\n\n".join(src["text"] for src in sources_metadata)
            if sources_metadata
            else ""
        )

        # ── Retrieval transparency logging ──
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

    # ── Policy Injection ──
    if intent in ["refund", "replacement", "warranty", "general_query"]:
        from . import supabase_client

        policies = supabase_client.get_policies()
        if policies:
            policy_texts = []
            for p in policies:
                ptype = p.get("policy_type", "").capitalize()
                scope = p.get("scope", "global")
                cat = p.get("category")
                desc = p.get("description", "")
                label = (
                    f"[{ptype} Policy - {scope.capitalize()}"
                    f"{' (' + cat + ')' if cat else ''}]"
                )
                policy_texts.append(f"{label}\n{desc}")

            if policy_texts:
                policy_block = (
                    "\n\n--- COMPANY POLICIES ---\n" + "\n\n".join(policy_texts)
                )
                context = (context + policy_block).strip()

    return {
        "context": context,
        "sources_metadata": sources_metadata,
        "search_ms": search_ms,
    }


def enforce_policy_node(state: AuraState) -> dict:
    """Deterministic policy enforcement — hard-coded Python, NOT an LLM call.

    Exact port of orchestrator.py lines 204–269.
    Checks the 30-day (or configured) refund/replacement window.
    """
    session = state["session"]
    intent = state["intent"]
    session_id = state["session_id"]

    policy_rejected = False
    should_skip_to_action = False
    verified_response = ""

    if session.get("order_id") and intent in [
        "refund",
        "replacement",
        "service_booking",
    ]:
        from . import supabase_client

        customer_name = session.get("customer_name", "Customer")
        product_name = session.get("product_name", "your product")
        order_id = session.get("order_id")
        purchase_date = session.get("purchase_date")
        product_id = session.get("product_id")

        # ── Deterministic Policy Enforcement ──
        policy_rejected_msg = None
        if intent in ["refund", "replacement"] and purchase_date:
            product_data = (
                supabase_client.get_product_by_id(product_id) if product_id else None
            )
            category = product_data.get("category", "") if product_data else ""

            policy = supabase_client.resolve_policy(category, intent)

            if policy and policy.get("rules"):
                window_days = policy["rules"].get("window_days")
                if window_days is not None:
                    try:
                        date_str = purchase_date.split("T")[0]
                        p_date = datetime.strptime(date_str, "%Y-%m-%d")
                        days_since = (datetime.now() - p_date).days
                        if days_since > window_days:
                            action_label = (
                                "refund" if intent == "refund" else "replacement"
                            )
                            policy_rejected_msg = (
                                f"I apologize, {customer_name}, but I cannot process "
                                f"a {action_label} for {product_name}. Our policy for "
                                f"this item allows {action_label}s within "
                                f"{window_days} days of purchase, and this order is "
                                f"{days_since} days old."
                            )
                    except Exception as e:
                        logger.error(
                            f"Error parsing date for policy check: {e}"
                        )

        if policy_rejected_msg:
            policy_rejected = True
            verified_response = policy_rejected_msg
            # Reset intent so action agent doesn't trigger
            session_manager.update_session(session_id, "pending_action", None)
            return {
                "policy_rejected": True,
                "should_skip_to_action": False,
                "verified_response": verified_response,
                "intent": "general_query",
            }
        else:
            should_skip_to_action = True
            action_labels = {
                "refund": "refund",
                "replacement": "replacement",
                "service_booking": "service appointment",
            }
            action_label = action_labels.get(intent, "request")

            verified_response = (
                f"Thank you, {customer_name}. I understand you'd like to proceed "
                f"with a {action_label} for {product_name} "
                f"(Order ID: {order_id}).\n\n"
                f"I'm processing your {action_label} request now. "
                f"Please wait a moment..."
            )

    return {
        "policy_rejected": policy_rejected,
        "should_skip_to_action": should_skip_to_action,
        "verified_response": verified_response,
    }


def respond_node(state: AuraState) -> dict:
    """Responder Agent — THE ONLY LLM CALL in the graph.

    Exact port of orchestrator.py lines 272–279.
    Skipped when policy_rejected or should_skip_to_action is True.
    """
    context = state.get("context", "")
    message = state["message"]
    session_context = state.get("session_context", "")
    session = state["session"]

    llm_start = time.time()
    try:
        draft_response = responder_agent(
            context,
            message,
            session_context,
            session.get("conversation_history", []),
        )
    except Exception as e:
        logger.error(f"Responder failed: {e}")
        draft_response = (
            "I apologize, but I'm experiencing technical difficulties. "
            "Please try again later."
        )
    llm_ms = (time.time() - llm_start) * 1000

    return {"verified_response": draft_response, "llm_ms": llm_ms}


def verify_node(state: AuraState) -> dict:
    """Verifier Agent — optional hallucination check (disabled by default).

    Exact port of orchestrator.py lines 281–286.
    """
    draft_response = state["verified_response"]
    context = state.get("context", "")

    try:
        verified_response = verifier_agent(draft_response, context)
    except Exception as e:
        logger.error(f"Verifier failed: {e}")
        verified_response = draft_response

    return {"verified_response": verified_response}


def decide_action_node(state: AuraState) -> dict:
    """Action Agent + Confirmation — deterministic lookup.

    Exact port of orchestrator.py lines 288–294.
    """
    intent = state["intent"]
    verified_response = state["verified_response"]

    action = action_agent(intent, verified_response)

    confirmation_message = None
    if action != "none":
        confirmation_message = action_confirmation_agent(action)

    return {"action": action, "confirmation_message": confirmation_message}


def execute_action_node(state: AuraState) -> dict:
    """Action execution + missing info check + email notification.

    Exact port of orchestrator.py lines 296–366.
    """
    action = state["action"]
    session_id = state["session_id"]
    session = state["session"]
    user = state.get("user")
    verified_response = state["verified_response"]
    message = state["message"]

    action_result = None

    if action != "none":
        session_manager.update_session(session_id, "pending_action", action)

        try:
            info_status = session_manager.check_missing_info_for_action(
                session_id, action
            )

            if not info_status["complete"]:
                # Append prompt instead of overwriting
                if (
                    verified_response
                    and len(message) > 10
                    and "?" in message
                ):
                    verified_response = (
                        f"{verified_response}\n\n{info_status['prompt']}"
                    )
                else:
                    verified_response = info_status["prompt"]
                action = "none"
            else:
                session_manager.update_session(
                    session_id, "pending_action", None
                )

                user_details = {
                    "email": session.get("customer_email")
                    or (user.get("email") if user else None),
                    "name": session.get("customer_name"),
                    "product_name": session.get("product_name"),
                    "order_id": session.get("order_id"),
                    "phone": session.get("customer_phone") or "",
                    "scheduled_date": session.get(
                        "preferred_datetime", "TBD"
                    ),
                    "time_slot": (
                        "As requested"
                        if session.get("preferred_datetime")
                        else "TBD"
                    ),
                }

                action_result = execute_action(action, user_details)

                if action_result and action_result.get("status") == "success":
                    action_id = action_result.get("action_id")

                    action_labels = {
                        "initiate_refund": "refund",
                        "initiate_replacement": "replacement",
                        "book_service": "service appointment",
                    }
                    action_label = action_labels.get(action, "request")

                    verified_response = (
                        f"Your {action_label} request has been processed.\n\n"
                        f"**Request ID:** {action_id}\n\n"
                        f"You'll receive confirmation via email shortly."
                    )

                    # Send email notification
                    user_email = user_details.get("email")
                    product_name = user_details.get(
                        "product_name", "Your Product"
                    )

                    try:
                        if action == "initiate_refund":
                            notifications.send_refund_confirmation_email(
                                action_id, product_name, user_email
                            )
                        elif action == "initiate_replacement":
                            notifications.send_replacement_confirmation_email(
                                action_id, product_name, user_email
                            )
                        elif action == "book_service":
                            booking_details = action_result.get("data", {})
                            notifications.send_service_booking_confirmation_email(
                                action_id, booking_details, user_email
                            )
                    except Exception as e:
                        logger.error(f"Email notification failed: {e}")

                    session_manager.mark_action_completed(
                        session_id, action_id, action
                    )

        except Exception as e:
            logger.error(f"Action execution failed: {e}", exc_info=True)
            action_result = {"status": "failed", "error": str(e)}
            verified_response += (
                "\n\nI apologize, but I encountered an error processing "
                "your request. Please try again or contact support directly."
            )

    return {
        "action": action,
        "action_result": action_result,
        "verified_response": verified_response,
    }


def persist_node(state: AuraState) -> dict:
    """Conversation persistence + citation building + performance logging.

    Exact port of orchestrator.py lines 368–396.
    """
    session_id = state["session_id"]
    user = state.get("user")
    verified_response = state["verified_response"]
    sources_metadata = state.get("sources_metadata", [])
    intent = state["intent"]
    use_rag = state.get("use_rag", False)
    context = state.get("context", "")
    action = state.get("action", "none")
    confirmation_message = state.get("confirmation_message")
    action_result = state.get("action_result")
    search_ms = state.get("search_ms", 0)
    llm_ms = state.get("llm_ms", 0)
    request_start = state["request_start"]

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
    session_manager.add_to_conversation_history(
        session_id, "assistant", verified_response, user, citations
    )

    # ── Structured request log ──
    total_ms = (time.time() - request_start) * 1000
    logger.info(
        f"[PERF] session={session_id[:20]} intent={intent} "
        f"rag={'yes' if use_rag else 'skip'} "
        f"search_ms={search_ms:.0f} llm_ms={llm_ms:.0f} total_ms={total_ms:.0f}"
    )

    response_dict = {
        "answer": verified_response,
        "intent": intent,
        "rag_sources": context[:500],
        "sources": citations,
        "action": action,
        "action_confirmation": confirmation_message,
        "action_log": action_result,
        "session_id": session_id,
    }

    return {"response_dict": response_dict}


# ══════════════════════════════════════════════════════════════
# CONDITIONAL EDGE FUNCTIONS
# ══════════════════════════════════════════════════════════════

def should_retrieve(state: AuraState) -> str:
    """Route: skip retrieval for greetings / short messages."""
    return "retrieve" if state.get("use_rag", False) else "enforce_policy"


def after_policy(state: AuraState) -> str:
    """Route after policy enforcement.

    - If policy rejected → skip LLM, go straight to decide_action
    - If should_skip_to_action → response already built, go to decide_action
    - Otherwise → run the LLM responder
    """
    if state.get("policy_rejected", False):
        return "decide_action"
    if state.get("should_skip_to_action", False):
        return "decide_action"
    return "respond"


def has_action(state: AuraState) -> str:
    """Route: execute action only if action != 'none'."""
    return "execute_action" if state.get("action", "none") != "none" else "persist"


# ══════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ══════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    """Construct and compile the AURA agent pipeline graph."""
    builder = StateGraph(AuraState)

    # ── Add nodes ────────────────────────────────────────────
    builder.add_node("load_session", load_session_node)
    builder.add_node("classify_intent", classify_intent_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("enforce_policy", enforce_policy_node)
    builder.add_node("respond", respond_node)
    builder.add_node("verify", verify_node)
    builder.add_node("decide_action", decide_action_node)
    builder.add_node("execute_action", execute_action_node)
    builder.add_node("persist", persist_node)

    # ── Add edges ────────────────────────────────────────────
    builder.add_edge(START, "load_session")
    builder.add_edge("load_session", "classify_intent")

    # Conditional: retrieve or skip to policy
    builder.add_conditional_edges(
        "classify_intent", should_retrieve, ["retrieve", "enforce_policy"]
    )

    builder.add_edge("retrieve", "enforce_policy")

    # Conditional: policy rejected / skip-to-action / normal respond
    builder.add_conditional_edges(
        "enforce_policy", after_policy, ["respond", "decide_action"]
    )

    builder.add_edge("respond", "verify")
    builder.add_edge("verify", "decide_action")

    # Conditional: has action to execute?
    builder.add_conditional_edges(
        "decide_action", has_action, ["execute_action", "persist"]
    )

    builder.add_edge("execute_action", "persist")
    builder.add_edge("persist", END)

    return builder


# ── Compile once at module level ─────────────────────────────
# MemorySaver is an in-memory checkpointer.  It enables resumability
# within a single process lifetime but does NOT survive server restarts.
# TODO: Replace with PostgresSaver backed by Supabase for production.
_checkpointer = MemorySaver()
_graph = _build_graph().compile(checkpointer=_checkpointer)


# ══════════════════════════════════════════════════════════════
# PUBLIC API — drop-in replacement for orchestrator.process_message
# ══════════════════════════════════════════════════════════════

def process_message(
    message: str, session_id: str = None, user: dict = None
) -> dict:
    """Process user message through the LangGraph AURA agent pipeline.

    This is a thin adapter that wraps the compiled graph invocation
    and returns the exact same response shape as orchestrator.py:
        {answer, intent, rag_sources, sources, action,
         action_confirmation, action_log, session_id}

    To switch main.py to use this module:
        from backend.orchestrator_graph import process_message
    """
    try:
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"

        initial_state: AuraState = {
            "message": message,
            "session_id": session_id,
            "user": user,
            # Defaults — populated by nodes
            "session": {},
            "session_context": "",
            "intent": "general_query",
            "use_rag": False,
            "context": "",
            "sources_metadata": [],
            "verified_response": "",
            "action": "none",
            "confirmation_message": None,
            "action_result": None,
            "policy_rejected": False,
            "should_skip_to_action": False,
            "search_ms": 0.0,
            "llm_ms": 0.0,
            "request_start": time.time(),
            "response_dict": {},
        }

        # Invoke the graph with the session_id as the thread_id
        # so the MemorySaver checkpointer groups messages by session.
        config = {"configurable": {"thread_id": session_id}}
        final_state = _graph.invoke(initial_state, config=config)

        return final_state.get("response_dict", {
            "answer": "I apologize, but I encountered an error processing your request.",
            "intent": "error",
            "rag_sources": "",
            "sources": [],
            "action": "none",
            "action_confirmation": None,
            "action_log": None,
            "session_id": session_id,
        })

    except Exception as e:
        logger.error(f"Critical error in process_message (graph): {e}", exc_info=True)
        return {
            "answer": "I apologize, but I encountered an error processing your request. Please try again.",
            "intent": "error",
            "rag_sources": "",
            "sources": [],
            "action": "none",
            "action_confirmation": None,
            "action_log": None,
            "session_id": session_id if session_id else "unknown",
        }
