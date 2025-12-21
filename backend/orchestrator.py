import logging
from .agents import (
    intent_agent,
    retrieval_agent,
    responder_agent,
    verifier_agent,
    action_agent,
    action_confirmation_agent,
    execute_action
)
from . import notifications
from . import session_manager
from . import order_lookup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_message(message, session_id=None):
    """Process user message through the AURA agent pipeline with session memory
    
    Flow: Session Check → Order Lookup → Intent → Retrieval → Responder → Verifier → Action → Execution → Notification
    """
    try:
        # Generate session_id if not provided
        if not session_id:
            import uuid
            session_id = f"session_{uuid.uuid4().hex[:12]}"
        
        logger.info(f"Processing message: {message[:50]}... | Session: {session_id}")
        
        # Get or create session
        session = session_manager.get_session(session_id)
        
        # Add user message to conversation history
        session_manager.add_to_conversation_history(session_id, "user", message)
        
        # Check for order_id in message
        extracted_order_id = order_lookup.extract_order_id_from_message(message)
        if extracted_order_id:
            logger.info(f"Detected order ID: {extracted_order_id}")
            
            # Fetch order details
            order_data = order_lookup.get_order_by_id(extracted_order_id)
            
            if order_data:
                # Store order data in session
                session_manager.update_session_bulk(session_id, {
                    "order_id": order_data.get("order_id"),
                    "customer_name": order_data.get("customer_name"),
                    "customer_email": order_data.get("customer_email"),
                    "customer_phone": order_data.get("customer_phone"),
                    "product_id": order_data.get("product_id"),
                    "product_name": order_data.get("product_name"),
                    "serial_number": order_data.get("serial_number"),
                    "purchase_date": order_data.get("purchase_date"),
                    "warranty_years": order_data.get("warranty_years")
                })
                logger.info(f"Order data stored in session for {order_data.get('customer_name')}")
            else:
                logger.warning(f"WARNING: Order {extracted_order_id} not found")
        
        # NEW: Extract reason or datetime from message (if Order ID already exists)
        if session.get("order_id") and not session.get("reason_for_action"):
            # If user is providing reason (not asking a question), store it
            if len(message) > 10 and not message.strip().endswith("?"):
                session_manager.update_session(session_id, "reason_for_action", message.strip())
                logger.info(f"Stored reason: {message[:50]}...")
        
        if session.get("order_id") and not session.get("preferred_datetime"):
            # Simple datetime detection (user mentioning dates/times)
            datetime_keywords = ["tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "next week", "pm", "am", "december", "january"]
            if any(keyword in message.lower() for keyword in datetime_keywords):
                session_manager.update_session(session_id, "preferred_datetime", message.strip())
                logger.info(f"Stored preferred datetime: {message[:50]}...")
        
        # Get session context for agents
        session_context = session_manager.get_session_context(session_id)
        
        # 1. Intent Agent - Classify user intent
        try:
            intent = intent_agent(message)
            logger.info(f"Intent: {intent}")
        except Exception as e:
            logger.error(f"Intent agent failed: {e}")
            intent = "general_query"

        # 2. Retrieval Agent - Get relevant context from knowledge base
        try:
            context = retrieval_agent(message)
            logger.info(f"Retrieved context: {len(context)} chars")
        except Exception as e:
            logger.error(f"Retrieval agent failed: {e}")
            context = ""

        # DETERMINISTIC FLOW CONTROLLER - Bypass LLM if info is complete
        should_skip_to_action = False
        
        # Check if we have complete order info and action intent
        if session.get("order_id") and intent in ["initiate_refund", "initiate_replacement", "book_service"]:
            logger.info("Flow Controller: Info complete + action intent detected -> Skipping to action")
            should_skip_to_action = True
            
            # Generate deterministic confirmation message
            customer_name = session.get("customer_name", "Customer")
            product_name = session.get("product_name", "your product")
            order_id = session.get("order_id")
            
            action_labels = {
                "initiate_refund": "refund",
                "initiate_replacement": "replacement",
                "book_service": "service appointment"
            }
            action_label = action_labels.get(intent, "request")
            
            draft_response = f"Thank you, {customer_name}. I understand you'd like to proceed with a {action_label} for {product_name} (Order ID: {order_id}).\n\n"
            draft_response += f"I'm processing your {action_label} request now. Please wait a moment..."
            
            verified_response = draft_response
        
        else:
            # 3. Responder Agent - Generate draft response (with session context)
            try:
                # Inject session context into responder
                draft_response = responder_agent(context, message, session_context)
                logger.info(f"Draft response generated ({len(draft_response)} chars)")
            except Exception as e:
                logger.error(f"Responder agent failed: {e}")
                draft_response = "I apologize, but I'm experiencing technical difficulties. Please try again later."

            # 4. Verifier Agent - Verify response quality and correctness
            try:
                verified_response = verifier_agent(draft_response, context)
                logger.info("Response verified")
            except Exception as e:
                logger.error(f"Verifier agent failed: {e}")
                verified_response = draft_response


        # 5. Action Agent - Decide if operational action is needed
        try:
            action = action_agent(intent, verified_response)
            logger.info(f"Action decided: {action}")
        except Exception as e:
            logger.error(f"Action agent failed: {e}")
            action = "none"

        # 6. Action Confirmation - Get user consent (optional)
        confirmation_message = None
        if action != "none":
            try:
                confirmation_message = action_confirmation_agent(action)
                logger.info(f"Confirmation message: {confirmation_message[:50] if confirmation_message else 'None'}...")
            except Exception as e:
                logger.error(f"Action confirmation failed: {e}")

        # 7. Action Execution - Execute if needed
        action_result = None
        email_result = None
        
        if action != "none":
            try:
                # NEW: Check if we need to collect more information
                info_status = session_manager.check_missing_info_for_action(session_id, action)
                
                if not info_status["complete"]:
                    # Information is incomplete - ask for what's missing
                    logger.info(f"Missing information for '{action}': {info_status['missing']}")
                    verified_response = info_status["prompt"]
                    action = "none"  # Don't execute yet
                    
                else:
                    # All information collected - proceed with execution
                    logger.info(f"All information collected for '{action}' - executing")
                    
                    # Use session data for user details
                    user_details = {
                        "email": session.get("customer_email"),
                        "name": session.get("customer_name"),
                        "product_name": session.get("product_name"),
                        "order_id": session.get("order_id"),
                        "phone": session.get("customer_phone") or ""
                    }
                    
                    # Execute the action
                    action_result = execute_action(action, user_details)
                    
                    # Build CLEAN confirmation message (NO technical details)
                    if action_result and action_result.get("status") == "success":
                        action_id = action_result.get("action_id")
                        
                        # Map action to human-readable label
                        action_labels = {
                            "initiate_refund": "refund",
                            "initiate_replacement": "replacement",
                            "book_service": "service appointment"
                        }
                        action_label = action_labels.get(action, "request")
                        
                        # CLEAN, MINIMAL confirmation message
                        verified_response = f"Your {action_label} request has been processed.\n\n"
                        verified_response += f"**Request ID:** {action_id}\n\n"
                        verified_response += f"You'll receive confirmation via email shortly."
                        
                        # Send email in BACKGROUND (user doesn't see this)
                        user_email = user_details.get("email")
                        product_name = user_details.get("product_name", "Your Product")
                        
                        try:
                            if action == "initiate_refund":
                                email_result = notifications.send_refund_confirmation_email(action_id, product_name, user_email)
                            elif action == "initiate_replacement":
                                email_result = notifications.send_replacement_confirmation_email(action_id, product_name, user_email)
                            elif action == "book_service":
                                booking_details = action_result.get("data", {})
                                email_result = notifications.send_service_booking_confirmation_email(action_id, booking_details, user_email)
                            
                            # Log email result (but don't show user)
                            if email_result and email_result.get("success"):
                                logger.info(f"Email sent successfully to {user_email}")
                            else:
                                logger.warning(f"Email sending issue: {email_result}")
                        except Exception as e:
                            # Log error but don't show user
                            logger.error(f"Email sending failed: {e}")
                        
                        # Mark action as completed in session
                        session_manager.mark_action_completed(session_id, action_id, action)
                    
            except Exception as e:
                logger.error(f"Action execution failed: {e}", exc_info=True)
                action_result = {"status": "failed", "error": str(e)}
                verified_response += f"\n\nI apologize, but I encountered an error processing your request. Please try again or contact support directly."


        # Add assistant response to conversation history
        session_manager.add_to_conversation_history(session_id, "assistant", verified_response)

        # Prepare result
        result = {
            "answer": verified_response,
            "intent": intent,
            "rag_sources": context[:500],  # Truncate for debug panel
            "action": action,
            "action_confirmation": confirmation_message,
            "action_log": action_result,
            "session_id": session_id
        }
        
        logger.info("Message processed successfully")
        return result
        
    except Exception as e:
        logger.error(f"ERROR: Critical error in process_message: {e}", exc_info=True)
        return {
            "answer": "I apologize, but I encountered an error processing your request. Please try again.",
            "intent": "error",
            "rag_sources": "",
            "action": "none",
            "action_confirmation": None,
            "action_log": None,
            "session_id": session_id if session_id else "unknown"
        }
