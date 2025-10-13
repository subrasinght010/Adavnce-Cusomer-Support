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
from nodes.unified_intelligence_agent import UnifiedIntelligenceAgent
from services.email_service import send_email
from state.workflow_state import OptimizedWorkflowState
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
        self.intelligence_agent = UnifiedIntelligenceAgent()
    
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
    
    async def check_inbox(self):
        """Check inbox for new emails"""
        try:
            # Connect if not connected
            if not self.imap_connection:
                self.imap_connection = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
                self.imap_connection.login(self.username, self.password)
            
            # Select inbox
            self.imap_connection.select('INBOX')
            
            # Search for unseen emails
            status, messages = self.imap_connection.search(None, 'UNSEEN')
            
            if status != 'OK':
                print("❌ Failed to search emails")
                return
            
            email_ids = messages[0].split()
            
            if not email_ids:
                return
            
            print(f"📬 Found {len(email_ids)} new email(s)")
            
            # Process each email
            for email_id in email_ids:
                try:
                    await self.process_email(email_id)
                except Exception as e:
                    print(f"❌ Failed to process email {email_id}: {e}")
        
        except Exception as e:
            print(f"❌ Inbox check failed: {e}")
            self.imap_connection = None
    
    async def process_email(self, email_id):
        """Process a single email"""
        try:
            # Fetch email
            status, msg_data = self.imap_connection.fetch(email_id, '(RFC822)')
            
            if status != 'OK':
                print(f"❌ Failed to fetch email {email_id}")
                return
            
            # Parse email
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            # Extract email details
            from_email = self._decode_header(email_message['From'])
            subject = self._decode_header(email_message['Subject'])
            
            # Extract sender email address
            sender_match = re.search(r'[\w\.-]+@[\w\.-]+', from_email)
            sender_email = sender_match.group(0) if sender_match else from_email
            
            # Get email body
            body = self._get_email_body(email_message)
            
            print(f"📧 Processing email from {sender_email}: {subject}")
            
            # Process with database
            async with AsyncSessionLocal() as db:
                db_manager = DBManager(db)
                
                # Get or create lead by email
                lead = await db_manager.get_lead_by_email(sender_email)
                if not lead:
                    lead = await db_manager.create_lead({
                        'email': sender_email,
                        'channel': 'email',
                        'status': 'new',
                        'created_at': datetime.utcnow()
                    })
                
                lead_id = str(lead.id)
                
                # Save incoming message
                await db_manager.create_conversation_message({
                    'lead_id': lead_id,
                    'message': f"Subject: {subject}\n\n{body}",
                    'direction': 'inbound',
                    'channel': 'email',
                    'timestamp': datetime.utcnow(),
                    'metadata': {'subject': subject}
                })
                
                # Build conversation history context
                context_builder = ContextBuilder(db_manager)
                conversation_history = await context_builder.get_conversation_context(
                    lead_id,
                    limit=10
                )
                
                # Create optimized workflow state
                state = OptimizedWorkflowState(
                    session_id=f"email_{email_id.decode()}",
                    lead_id=lead_id,
                    current_message=body,
                    channel="email",
                    conversation_history=conversation_history,
                    lead_context={
                        'email': sender_email,
                        'status': lead.status,
                        'previous_interactions': len(conversation_history),
                        'subject': subject
                    }
                )
                
                # Process with unified intelligence agent
                print(f"🤖 Processing with Unified Intelligence Agent...")
                result_state = await self.intelligence_agent.execute(state)
                
                # Extract response from intelligence output
                intelligence_output = result_state.get('intelligence_output', {})
                response_text = intelligence_output.get('response_text',
                    'Thank you for your email. Our team will get back to you shortly.')
                
                # Send email response
                email_sent = await send_email(
                    to_email=sender_email,
                    subject=f"Re: {subject}",
                    body=response_text
                )
                
                if email_sent:
                    # Save outbound message
                    await db_manager.create_conversation_message({
                        'lead_id': lead_id,
                        'message': response_text,
                        'direction': 'outbound',
                        'channel': 'email',
                        'timestamp': datetime.utcnow()
                    })
                    
                    # Update lead with latest intent and sentiment
                    await db_manager.update_lead(lead_id, {
                        'last_contacted': datetime.utcnow(),
                        'last_message': body,
                        'last_intent': intelligence_output.get('intent', 'unknown'),
                        'last_sentiment': intelligence_output.get('sentiment', 'neutral'),
                        'status': 'engaged'
                    })
                    
                    print(f"✅ Email response sent to {sender_email}")
        
        except Exception as e:
            print(f"❌ Email processing error: {e}")
            import traceback
            traceback.print_exc()
    
    def _decode_header(self, header_value):
        """Decode email header"""
        if not header_value:
            return ""
        
        decoded_parts = decode_header(header_value)
        decoded_string = ""
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_string += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                decoded_string += part
        
        return decoded_string
    
    def _get_email_body(self, email_message):
        """Extract email body text"""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Get text/plain parts
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode(errors='ignore')
                        break
                    except:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode(errors='ignore')
            except:
                body = str(email_message.get_payload())
        
        return body.strip()


# Singleton instance
email_monitor = EmailMonitor()