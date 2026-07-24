"""
AURA Backend — Order Lookup

Purpose:
    Find orders in the database and extract order IDs from natural
    language messages.

Responsibilities:
    - Fetch a single order by ID from Supabase
    - Extract order IDs (e.g. "ORD201", "ORD-201") from free-text
      user messages using regex patterns

Workflow:
    User says "I need help with order ORD-301"
        │
        ▼
    extract_order_id_from_message()  →  "ORD301"
        │
        ▼
    get_order_by_id("ORD301")  →  { id, customer_name, product_name, ... }

Used By:
    orchestrator.py  (extracts order ID → fetches order data → passes to agents)

Depends On:
    supabase_client.py

Related Files:
    orchestrator.py     — calls both functions
    session_manager.py  — stores order data in session state
    supabase_client.py  — provides get_order_by_id_db()
"""

import logging
import re
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from . import supabase_client


# ==========================================================
# ORDER RETRIEVAL
# ==========================================================

def get_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch order details from Supabase by order ID.

    Called By:  orchestrator.py → process_message()
    Calls:     supabase_client.get_order_by_id_db()
    Returns:   Order dict if found, None otherwise.
    """
    try:
        order_id_clean = order_id.strip().upper()
        order = supabase_client.get_order_by_id_db(order_id_clean)

        if order:
            logger.info(f"Found order in DB: {order_id_clean}")
            return order

        logger.warning(f"WARNING: Order not found in DB: {order_id_clean}")
        return None

    except Exception as e:
        logger.error(f"ERROR: Error fetching order {order_id}: {e}")
        return None


# ==========================================================
# ORDER ID EXTRACTION (from natural language)
# ==========================================================

def extract_order_id_from_message(message: str) -> Optional[str]:
    """
    Extract an order ID from the user's message using regex.

    Why?
        Users type order IDs in many formats: "ORD201", "ORD-201",
        "order id: ORD 201", "my order is ORD201".  This function
        normalizes all of them into a clean "ORD201" format.

    Called By:  orchestrator.py → process_message()
    Returns:   Normalized order ID string, or None if not found.
    """
    try:
        patterns = [
            r'ORD[-\s]?(\d+)',                                  # ORD201, ORD-201, ORD 201
            r'order\s*(?:id|number|#)?\s*:?\s*(ORD[-\s]?\d+)',  # order id: ORD201
            r'my\s*order\s*(?:is|id)?\s*(ORD[-\s]?\d+)'        # my order is ORD201
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                if len(match.groups()) > 0:
                    order_id = match.group(1) if match.lastindex == 1 else match.group(0)
                else:
                    order_id = match.group(0)

                # Normalize: remove spaces/hyphens, ensure ORD prefix
                order_id = order_id.replace(" ", "").replace("-", "").upper()
                if not order_id.startswith("ORD"):
                    order_id = "ORD" + order_id

                logger.info(f"📝 Extracted order ID: {order_id}")
                return order_id

        return None

    except Exception as e:
        logger.error(f"ERROR: Error extracting order ID: {e}")
        return None
