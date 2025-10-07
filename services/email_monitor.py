"""
Email Monitor - Continuously monitors email inbox for new messages
"""

import imaplib
import email
from email.header import decode_header
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import re
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.context_builder import ContextBuilder
from nodes.intent_detector import intent_detector_llm
from services.email_service import send_email
from state.workflow_state import WorkflowState
import os


class EmailMonitor:
    def __init__(self):
        self.imap_server = os.getenv('EMAIL_IMAP_SERVER', 'imap.gmail.com')
        self.imap_port = int(os.getenv('EMAIL_IMAP_PORT', '993'))
        self.username = os.getenv('EMAIL_USERNAME')
        self.password = os.getenv('EMAIL_PASSWORD')
        self.check_interval = int(os.getenv('EMAIL_CHECK_INTERVAL', '30'))
        self.imap_connection = None
        self.is_running = False
        self.last_check_time = None
    
    async def start_monitoring(self):
        """Start email monitoring loop"""
        if not self.username or not self.password:
            print("❌ Email credentials not configured. Skipping email monitoring.")
            return
        
        self.is_running = True
        print(f"📧 Email monitor started. Checking every {self.check_interval} seconds.")
        
        while self.is_running:
            try:
                await self.check_inbox()
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                print(f"❌ Email monitoring error: {e}")
                await asyncio.sleep(60)  # Wait longer on error
                
                # Try to reconnect
                if self.imap_connection:
                    try:
                        self.imap_connection.logout()
                    except:
                        pass
                    self.imap_connection = None
    
    def stop_monitoring(self):
        """Stop email monitoring"""
        self.is_running = False
        if self.imap_connection:
            try:
                self.imap_connection.logout()
            except:
                pass
        print("📧 Email monitor stopped.")
    
    def connect_to_imap(self):
        """Connect to IMAP server"""
        try:
            if self.imap_connection:
                # Test if connection is alive
                try:
                    self.imap_connection.noop()
                    return self.imap_connection
                except:
                    self.imap_connection = None
            
            # Create new connection
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.username, self.password)
            mail.select('INBOX')
            
            self.imap_connection = mail
            return mail
            
        except Exception as e:
            print(f"❌ IMAP connection error: {e}")
            return None
    
    async def check_inbox(self):
        """Check inbox for new messages"""
        try:
            mail = self.connect_to_imap()
            if not mail:
                return
            
            # Search for unseen messages
            status, message_ids = mail.search(None, 'UNSEEN')
            
            if status != 'OK':
                print("❌ Failed to search inbox")
                return
            
            # Get list of message IDs
            message_id_list = message_ids[0].split()
            
            if not message_id_list:
                # No new messages
                return
            
            print(f"📬 Found {len(message_id_list)} new email(s)")
            
            # Process each new email
            for msg_id in message_id_list:
                try:
                    await self.process_email(mail, msg_id)
                except Exception as e:
                    print(f"❌ Error processing email {msg_id}: {e}")
            
            self.last_check_time = datetime.now()
            
        except Exception as e:
            print(f"❌ Error checking inbox: {e}")
    
    async def process_email(self, mail, msg_id):
        """Process a single email"""
        try:
            # Fetch email
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            
            if status != 'OK':
                return
            
            # Parse email
            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            # Extract email data
            email_data = self.extract_email_data(email_message)
            
            print(f"📨 Processing email from: {email_data['from_email']}")
            print(f"   Subject: {email_data['subject']}")
            
            # Process asynchronously
            await self._process_email_async(email_data)
            
            # Mark as read
            mail.store(msg_id, '+FLAGS', '\\Seen')
            
        except Exception as e:
            print(f"❌ Error processing email: {e}")
            import traceback
            traceback.print_exc()
    
    def extract_email_data(self, email_message) -> Dict:
        """Extract data from email message"""
        # Get sender
        from_header = email_message.get('From', '')
        from_email = self._extract_email_address(from_header)
        from_name = self._extract_name(from_header)
        
        # Get subject
        subject = self._decode_header(email_message.get('Subject', ''))
        
        # Get message ID (for threading)
        message_id = email_message.get('Message-ID', '').strip('<>')
        in_reply_to = email_message.get('In-Reply-To', '').strip('<>')
        references = email_message.get('References', '')
        
        # Get body
        body = self._get_email_body(email_message)
        
        # Get timestamp
        date_str = email_message.get('Date', '')
        timestamp = email.utils.parsedate_to_datetime(date_str) if date_str else datetime.now()
        
        return {
            'from_email': from_email,
            'from_name': from_name,
            'subject': subject,
            'body': body,
            'message_id': message_id,
            'in_reply_to': in_reply_to,
            'references': references,
            'timestamp': timestamp
        }
    
    def _extract_email_address(self, header: str) -> str:
        """Extract email address from header"""
        match = re.search(r'[\w\.-]+@[\w\.-]+', header)
        return match.group(0) if match else ''
    
    def _extract_name(self, header: str) -> str:
        """Extract name from email header"""
        if '<' in header:
            name = header.split('<')[0].strip().strip('"')
            return name if name else 'Unknown'
        return 'Unknown'
    
    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        if not header:
            return ''
        
        decoded_parts = decode_header(header)
        decoded_str = ''
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_str += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                decoded_str += part
        
        return decoded_str
    
    def _get_email_body(self, email_message) -> str:
        """Extract email body"""
        body = ''
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))
                
                # Skip attachments
                if 'attachment' in content_disposition:
                    continue
                
                # Get text/plain or text/html
                if content_type == 'text/plain':
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        pass
                elif content_type == 'text/html' and not body:
                    try:
                        html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        body = self._html_to_text(html_body)
                    except:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                body = str(email_message.get_payload())
        
        return body.strip()
    
    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (simple version)"""
        # Remove HTML tags
        text = re.sub('<[^<]+?>', '', html)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    async def _process_email_async(self, email_data: Dict):
        """Process email asynchronously with AI response"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            context_builder = ContextBuilder(db)
            
            try:
                # Find or create lead
                lead = await db.get_or_create_lead(
                    email=email_data['from_email'],
                    name=email_data['from_name']
                )
                
                print(f"✅ Lead identified: {lead.id} - {lead.name}")
                
                # Check if this is a reply to previous email
                parent_message_id = None
                if email_data['in_reply_to']:
                    parent_conv = await db.get_conversation_by_message_id(
                        email_data['in_reply_to']
                    )
                    if parent_conv:
                        parent_message_id = parent_conv.id
                        print(f"🔗 Email is reply to conversation #{parent_message_id}")
                
                # Save incoming email
                await db.add_conversation(
                    lead_id=lead.id,
                    message=f"Subject: {email_data['subject']}\n\n{email_data['body']}",
                    channel='email',
                    sender='user',
                    message_id=email_data['message_id'],
                    parent_message_id=parent_message_id,
                    metadata={
                        'subject': email_data['subject'],
                        'references': email_data['references']
                    }
                )
                
                # Build context
                context = await context_builder.build_context_for_ai(
                    lead_id=lead.id,
                    current_message=email_data['body'],
                    channel='email',
                    max_messages=10
                )
                
                print(f"📋 Context built: {context['conversation_type']}")
                
                # Create workflow state
                state = WorkflowState(
                    lead_id=str(lead.id),
                    lead_data={
                        'name': lead.name,
                        'phone': lead.phone,
                        'email': lead.email
                    },
                    client_type=lead.client_type or 'existing',
                    conversation_thread=[
                        f"User (Email): {email_data['subject']}",
                        email_data['body']
                    ],
                    preferred_channel='email',
                    lead_status=lead.lead_status,
                    db_log=[],
                    channel_history=['email']
                )
                
                # Run intent detection
                updated_state = intent_detector_llm(state)
                
                # Get AI response
                ai_response = updated_state.get('agent_response') or \
                             updated_state.get('conversation_thread', [])[-1] if updated_state.get('conversation_thread') else \
                             "Thank you for your email. How can I assist you?"
                
                # Clean AI response
                if ':' in ai_response:
                    ai_response = ai_response.split(':', 1)[1].strip()
                
                print(f"🤖 AI Response: {ai_response[:100]}...")
                
                # Generate reply subject
                reply_subject = email_data['subject']
                if not reply_subject.startswith('RE:'):
                    reply_subject = f"RE: {reply_subject}"
                
                # Build HTML email body
                email_body = self._build_email_body(
                    lead_name=lead.name,
                    ai_response=ai_response
                )
                
                # Send email reply
                success = await send_email(
                    to=email_data['from_email'],
                    subject=reply_subject,
                    body=email_body
                )
                
                if success:
                    # Save AI response
                    await db.add_conversation(
                        lead_id=lead.id,
                        message=ai_response,
                        channel='email',
                        sender='ai',
                        parent_message_id=parent_message_id,
                        intent_detected=updated_state.get('intent_detected'),
                        metadata={'subject': reply_subject}
                    )
                    
                    # Update lead
                    lead.last_contacted_at = datetime.now()
                    lead.response_received = True
                    await session.commit()
                    
                    print(f"✅ Email reply sent successfully")
                else:
                    print(f"❌ Failed to send email reply")
                
            except Exception as e:
                print(f"❌ Error processing email: {e}")
                import traceback
                traceback.print_exc()
    
    def _build_email_body(self, lead_name: str, ai_response: str) -> str:
        """Build HTML email body"""
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
            <p>Dear {lead_name},</p>
            
            <p>{ai_response}</p>
            
            <br>
            <p>Best regards,<br>
            <strong>TechCorp Support Team</strong></p>
            
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                This is an automated response from our AI assistant. 
                If you need further assistance, please reply to this email.
            </p>
        </body>
        </html>
        """
        return html


# Singleton instance
email_monitor = EmailMonitor()