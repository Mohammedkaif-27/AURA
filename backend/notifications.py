import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@aura-support.com")


def send_email(to_email: str, subject: str, html_content: str) -> dict:
    """Send email using SMTP - Returns detailed status"""
    try:
        if not SMTP_USERNAME or not SMTP_PASSWORD:
            logger.warning("WARNING: Email credentials not configured. Email not sent.")
            return {
                "success": False,
                "error": "Email service not configured",
                "message": "Email credentials missing in .env file"
            }
        
        if not to_email:
            logger.error("ERROR: No recipient email provided")
            return {
                "success": False,
                "error": "No recipient email",
                "message": "Recipient email address is missing"
            }
        
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = SENDER_EMAIL
        message["To"] = to_email
        
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        
        logger.info(f"Email sent successfully to {to_email}")
        return {
            "success": True,
            "message": f"Email sent to {to_email}",
            "recipient": to_email
        }
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"ERROR: SMTP authentication failed: {e}")
        return {
            "success": False,
            "error": "Authentication failed",
            "message": "Email service authentication failed. Please check SMTP credentials."
        }
    except smtplib.SMTPException as e:
        logger.error(f"ERROR: SMTP error: {e}")
        return {
            "success": False,
            "error": "SMTP error",
            "message": f"Email service error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"ERROR: Failed to send email: {e}")
        return {
            "success": False,
            "error": "Unknown error",
            "message": f"Failed to send email: {str(e)}"
        }


def send_refund_confirmation_email(refund_id: str, product_name: str, user_email: str):
    """Send refund confirmation email"""
    subject = f"Refund Request Confirmed - {refund_id}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #195de6;">Refund Request Confirmed</h2>
            
            <p>Dear Customer,</p>
            
            <p>Your refund request has been successfully initiated. Here are the details:</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Request ID:</strong> {refund_id}</p>
                <p><strong>Product:</strong> {product_name}</p>
                <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
                <p><strong>Status:</strong> Processing</p>
            </div>
            
            <h3 style="color: #195de6;">Next Steps:</h3>
            <ul>
                <li>Your refund request is being reviewed by our team</li>
                <li>You will receive an update within 3-5 business days</li>
                <li>The refund will be processed to your original payment method</li>
            </ul>
            
            <p>If you have any questions, please contact our support team with your request ID.</p>
            
            <p style="margin-top: 30px;">
                Best regards,<br>
                <strong>AURA Support Team</strong>
            </p>
            
            <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #777;">
                This is an automated message. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(user_email, subject, html_content)


def send_replacement_confirmation_email(replacement_id: str, product_name: str, user_email: str):
    """Send replacement confirmation email"""
    subject = f"Replacement Request Confirmed - {replacement_id}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #195de6;">Replacement Request Confirmed</h2>
            
            <p>Dear Customer,</p>
            
            <p>Your replacement request has been successfully initiated. Here are the details:</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Request ID:</strong> {replacement_id}</p>
                <p><strong>Product:</strong> {product_name}</p>
                <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
                <p><strong>Status:</strong> Processing</p>
            </div>
            
            <h3 style="color: #195de6;">Next Steps:</h3>
            <ul>
                <li>Your replacement request is being processed</li>
                <li>Our team will contact you within 2-3 business days</li>
                <li>Product pickup will be scheduled at your convenience</li>
                <li>Replacement unit will be dispatched after verification</li>
            </ul>
            
            <p>If you have any questions, please contact our support team with your request ID.</p>
            
            <p style="margin-top: 30px;">
                Best regards,<br>
                <strong>AURA Support Team</strong>
            </p>
            
            <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #777;">
                This is an automated message. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(user_email, subject, html_content)


def send_service_booking_confirmation_email(service_id: str, booking_details: dict, user_email: str):
    """Send service booking confirmation email"""
    subject = f"Service Booking Confirmed - {service_id}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #195de6;">Service Appointment Confirmed</h2>
            
            <p>Dear Customer,</p>
            
            <p>Your service appointment has been successfully booked. Here are the details:</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Booking ID:</strong> {service_id}</p>
                <p><strong>Product:</strong> {booking_details.get('product_name', 'N/A')}</p>
                <p><strong>Service Center:</strong> {booking_details.get('service_center', 'N/A')}</p>
                <p><strong>Scheduled Date:</strong> {booking_details.get('scheduled_date', 'N/A')}</p>
                <p><strong>Time Slot:</strong> {booking_details.get('time_slot', 'N/A')}</p>
            </div>
            
            <h3 style="color: #195de6;">Important Information:</h3>
            <ul>
                <li>Please arrive 10 minutes before your scheduled time</li>
                <li>Bring your product and proof of purchase</li>
                <li>Have your booking ID ready at the service center</li>
                <li>If you need to reschedule, contact us at least 24 hours in advance</li>
            </ul>
            
            <p>If you have any questions, please contact our support team with your booking ID.</p>
            
            <p style="margin-top: 30px;">
                Best regards,<br>
                <strong>AURA Support Team</strong>
            </p>
            
            <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
            <p style="font-size: 12px; color: #777;">
                This is an automated message. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(user_email, subject, html_content)
