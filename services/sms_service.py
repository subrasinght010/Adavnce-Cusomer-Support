"""
SMS Service - Twilio
"""

import os
from twilio.rest import Client

# Initialize Twilio client
twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

async def send_sms(to: str, message: str) -> bool:
    """
    Send SMS using Twilio
    
    Args:
        to: Phone number (E.164 format: +91XXXXXXXXXX)
        message: SMS content (max 160 chars recommended)
    """
    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=os.getenv("TWILIO_PHONE_NUMBER"),
            to=to
        )
        
        print(f"✅ SMS sent to {to}: {msg.sid}")
        return True
    
    except Exception as e:
        print(f"❌ SMS send error: {e}")
        return False


def get_sms_template(template_name: str, **kwargs) -> str:
    """
    Get SMS template (160 char limit)
    
    Args:
        template_name: Template name
        **kwargs: Template variables
    """
    templates = {
        "callback_confirmation": "Your callback is scheduled for {callback_time}. We'll call you at {phone}. - TechCorp",
        
        "pricing_sent": "Pricing details sent to your email. Check inbox. Questions? Call us at {support_number}. - TechCorp",
        
        "general_confirmation": "Your request has been received. We'll get back to you shortly. - TechCorp",
        
        "order_update": "Order #{order_id} status: {status}. Track at {tracking_link}. - TechCorp"
    }
    
    template = templates.get(template_name, templates["general_confirmation"])
    message = template.format(**kwargs)
    
    # Truncate if too long
    if len(message) > 160:
        message = message[:157] + "..."
    
    return message