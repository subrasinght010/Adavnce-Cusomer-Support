# services/email_service.py
"""Email Service - SendGrid with Attachment Support"""

import os
import base64
from typing import Optional
from pathlib import Path
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition

async def send_email(
    to: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    thread_id: Optional[str] = None,
    reply_to_message_id: Optional[str] = None
) -> bool:
    """Send email without attachment"""
    return await send_email_with_attachment(
        to=to,
        subject=subject,
        body=body,
        from_email=from_email,
        thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        attachment_path=None
    )


async def send_email_with_attachment(
    to: str,
    subject: str,
    body: str,
    attachment_paths: Optional[list] = None,
    from_email: Optional[str] = None,
    thread_id: Optional[str] = None,
    reply_to_message_id: Optional[str] = None
) -> bool:
    """
    Send email with multiple attachments using SendGrid
    
    Args:
        to: Recipient email
        subject: Email subject
        body: HTML body content
        attachment_paths: List of file paths to attach (optional)
        from_email: Sender email (optional)
        thread_id: Email thread ID for threading
        reply_to_message_id: Message ID to reply to
    """
    try:
        from_email = from_email or os.getenv("FROM_EMAIL", "support@techcorp.com")
        
        message = Mail(
            from_email=Email(from_email),
            to_emails=To(to),
            subject=subject,
            html_content=Content("text/html", body)
        )
        
        # Add threading headers
        if reply_to_message_id:
            message.reply_to = reply_to_message_id
            message.custom_args = {"In-Reply-To": reply_to_message_id}
        
        if thread_id:
            if not message.custom_args:
                message.custom_args = {}
            message.custom_args["References"] = thread_id
        
        # Add multiple attachments
        if attachment_paths:
            for attachment_path in attachment_paths:
                if Path(attachment_path).exists():
                    with open(attachment_path, 'rb') as f:
                        file_data = f.read()
                        encoded_file = base64.b64encode(file_data).decode()
                        
                        file_name = Path(attachment_path).name
                        file_type = _get_mime_type(attachment_path)
                        
                        attached_file = Attachment(
                            FileContent(encoded_file),
                            FileName(file_name),
                            FileType(file_type),
                            Disposition('attachment')
                        )
                        message.add_attachment(attached_file)
                        
                        print(f"📎 Attached: {file_name} ({file_type})")
        
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        
        print(f"✅ Email sent to {to}: {response.status_code}")
        return response.status_code in [200, 202]
    
    except Exception as e:
        print(f"❌ Email send error: {e}")
        return False


def _get_mime_type(file_path: str) -> str:
    """Get MIME type from file extension"""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    
    if mime_type:
        return mime_type
    
    # Fallback for common types
    ext = Path(file_path).suffix.lower()
    mime_map = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png'
    }
    
    return mime_map.get(ext, 'application/octet-stream')