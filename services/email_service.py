"""
Email Service - SendGrid/SMTP
"""

import os
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

async def send_email(
    to: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None
) -> bool:
    """
    Send email using SendGrid
    
    Args:
        to: Recipient email
        subject: Email subject
        body: HTML body content
        from_email: Sender email (optional)
    """
    try:
        from_email = from_email or os.getenv("FROM_EMAIL", "support@techcorp.com")
        
        message = Mail(
            from_email=Email(from_email),
            to_emails=To(to),
            subject=subject,
            html_content=Content("text/html", body)
        )
        
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        
        print(f"✅ Email sent to {to}: {response.status_code}")
        return response.status_code in [200, 202]
    
    except Exception as e:
        print(f"❌ Email send error: {e}")
        return False


def get_email_template(template_name: str, **kwargs) -> str:
    """
    Get email template and populate with data
    
    Args:
        template_name: Template name (pricing_details, callback_confirmation, etc.)
        **kwargs: Template variables
    """
    templates = {
        "pricing_details": """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>TechCorp Pricing Details</h2>
            <p>Dear {name},</p>
            <p>Thank you for your interest in our products. Please find our pricing details below:</p>
            {pricing_content}
            <p>If you have any questions, feel free to reach out!</p>
            <p>Best regards,<br>TechCorp Support Team</p>
        </body>
        </html>
        """,
        
        "callback_confirmation": """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Callback Scheduled</h2>
            <p>Dear {name},</p>
            <p>Your callback has been scheduled for:</p>
            <p style="font-size: 18px; font-weight: bold;">{callback_time}</p>
            <p>We'll call you at: {phone}</p>
            <p>Best regards,<br>TechCorp Support Team</p>
        </body>
        </html>
        """,
        
        "product_catalog": """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Product Catalog</h2>
            <p>Dear {name},</p>
            <p>Thank you for your interest! Please find attached our latest product catalog.</p>
            <p>Explore our range of products and let us know if you have any questions.</p>
            <p>Best regards,<br>TechCorp Support Team</p>
        </body>
        </html>
        """
    }
    
    template = templates.get(template_name, templates["pricing_details"])
    return template.format(**kwargs)