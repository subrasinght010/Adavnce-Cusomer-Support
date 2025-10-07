"""
WhatsApp Service - Twilio WhatsApp API
"""

import os
from twilio.rest import Client

# Initialize Twilio client
twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

async def send_whatsapp(to: str, message: str, media_url: str = None) -> bool:
    """
    Send WhatsApp message using Twilio
    
    Args:
        to: WhatsApp number (E.164 format: +91XXXXXXXXXX)
        message: Message content
        media_url: Optional URL to PDF/image
    """
    try:
        msg_params = {
            "body": message,
            "from_": os.getenv("TWILIO_WHATSAPP_NUMBER"),
            "to": f"whatsapp:{to}"
        }
        
        if media_url:
            msg_params["media_url"] = [media_url]
        
        msg = twilio_client.messages.create(**msg_params)
        
        print(f"✅ WhatsApp sent to {to}: {msg.sid}")
        return True
    
    except Exception as e:
        print(f"❌ WhatsApp send error: {e}")
        return False


def get_whatsapp_template(template_name: str, **kwargs) -> str:
    """
    Get WhatsApp message template
    
    Args:
        template_name: Template name
        **kwargs: Template variables
    """
    templates = {
        "product_catalog": """Hi {name}! 👋

        Here's our product catalog as requested.

        📦 Explore our range of products
        💰 Competitive pricing
        🚚 Fast delivery

        Feel free to ask if you have any questions!

        Best regards,
        TechCorp Team""",
                
                "pricing_details": """Hi {name}! 👋

        Here are the pricing details you requested:

        {pricing_content}

        Questions? Just reply to this message!

        Best regards,
        TechCorp Team""",
                
                "callback_confirmation": """Hi {name}! 👋

        Your callback is confirmed for:
        📅 {callback_time}
        📞 {phone}

        We'll call you then!

        Best regards,
        TechCorp Team"""
            }
    
    template = templates.get(template_name, templates["product_catalog"])
    return template.format(**kwargs)