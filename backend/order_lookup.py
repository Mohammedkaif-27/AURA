import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to orders.json
ORDERS_FILE = Path(__file__).parent / "data" / "orders.json"


def load_orders() -> list:
    """Load all orders from orders.json"""
    try:
        if not ORDERS_FILE.exists():
            logger.error(f"Orders file not found: {ORDERS_FILE}")
            return []
        
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            orders = json.load(f)
        
        logger.info(f"Loaded {len(orders)} orders from {ORDERS_FILE.name}")
        return orders
        
    except Exception as e:
        logger.error(f"ERROR: Error loading orders: {e}")
        return []


from . import supabase_client

def get_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    """Fetch order details by order_id from Supabase"""
    try:
        # Normalize order_id (remove spaces, uppercase)
        order_id_clean = order_id.strip().upper()
        
        # Use Supabase directly instead of local JSON
        order = supabase_client.get_order_by_id_db(order_id_clean)
        
        if order:
            logger.info(f"Found order in DB: {order_id_clean}")
            return order
            
        logger.warning(f"WARNING: Order not found in DB: {order_id_clean}")
        return None
        
    except Exception as e:
        logger.error(f"ERROR: Error fetching order {order_id}: {e}")
        return None
        return None


def validate_order_exists(order_id: str) -> bool:
    """Check if an order exists"""
    order = get_order_by_id(order_id)
    return order is not None


def extract_order_id_from_message(message: str) -> Optional[str]:
    """Extract order ID from user message using regex"""
    try:
        # Pattern: ORD followed by digits, e.g., ORD201, ORD-201, ORD 201
        patterns = [
            r'ORD[-\s]?(\d+)',  # ORD201, ORD-201, ORD 201
            r'order\s*(?:id|number|#)?\s*:?\s*(ORD[-\s]?\d+)',  # order id: ORD201
            r'my\s*order\s*(?:is|id)?\s*(ORD[-\s]?\d+)'  # my order is ORD201
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                # Normalize the order ID
                if len(match.groups()) > 0:
                    order_id = match.group(1) if match.lastindex == 1 else match.group(0)
                else:
                    order_id = match.group(0)
                
                # Clean up: remove spaces and hyphens, ensure ORD prefix
                order_id = order_id.replace(" ", "").replace("-", "").upper()
                if not order_id.startswith("ORD"):
                    order_id = "ORD" + order_id
                
                logger.info(f"📝 Extracted order ID: {order_id}")
                return order_id
        
        return None
        
    except Exception as e:
        logger.error(f"ERROR: Error extracting order ID: {e}")
        return None


def get_order_summary(order: Dict[str, Any]) -> str:
    """Format order details as a readable summary"""
    try:
        summary = f"""
Order Details:
- Order ID: {order.get('id', 'N/A')}
- Customer: {order.get('customer_name', 'N/A')}
- Product: {order.get('product_name', 'N/A')}
- Model: {order.get('product_id', 'N/A')}
- Purchase Date: {order.get('purchase_date', 'N/A')}
- Warranty: {order.get('warranty_years', 'N/A')} years
"""
        return summary.strip()
        
    except Exception as e:
        logger.error(f"ERROR: Error creating order summary: {e}")
        return "Order details unavailable"
