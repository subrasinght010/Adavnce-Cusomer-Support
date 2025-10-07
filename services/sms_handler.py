"""
SMS Handler - Processes incoming SMS webhooks from Twilio
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.context_builder import ContextBuilder
from nodes.intent_detector import intent_detector_llm
from services.sms_service import send_sms
from state.workflow_state import WorkflowState, lead_reducer


class SMSHandler:
    def __init__(self):
        self.processing_lock = asyncio.Lock()
    
    async def handle_incoming_sms(self, webhook_data: Dict) -> Dict:
        """
        Process incoming SMS from Twilio webhook
        
        Args:
            webhook_data: Data from Twilio webhook
            {
                'From': '+919876543210',
                'To': '+1234567890',
                'Body': 'User message',
                'MessageSid': 'SM1234...'
            }
        
        Returns:
            Response dictionary
        """
        try:
            # Extract data
            from_number = webhook_data.get('From', '').strip()
            message_body = webhook_data.get('Body', '').strip()
            message_sid = webhook_data.get('MessageSid', '')
            
            if not from_number or not message_body:
                return {
                    'status': 'error',
                    'message': 'Missing required fields'
                }
            
            print(f"📱 SMS received from {from_number}: {message_body}")
            
            # Process in background to not block webhook response
            asyncio.create_task(
                self._process_sms_async(from_number, message_body, message_sid)
            )
            
            return {
                'status': 'success',
                'message': 'SMS received and processing'
            }
            
        except Exception as e:
            print(f"❌ Error handling SMS: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def _process_sms_async(
        self,
        phone_number: str,
        message: str,
        message_sid: str
    ):
        """Process SMS asynchronously"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            context_builder = ContextBuilder(db)
            
            try:
                # Find or create lead
                lead = await db.get_or_create_lead(
                    phone=phone_number,
                    name=f"SMS User {phone_number[-4:]}"
                )
                
                print(f"✅ Lead identified: {lead.id} - {lead.name}")
                
                # Save incoming message
                await db.add_conversation(
                    lead_id=lead.id,
                    message=message,
                    channel='sms',
                    sender='user',
                    message_id=message_sid
                )
                
                # Build context
                context = await context_builder.build_context_for_ai(
                    lead_id=lead.id,
                    current_message=message,
                    channel='sms',
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
                        f"User (SMS): {message}"
                    ],
                    preferred_channel='sms',
                    lead_status=lead.lead_status,
                    db_log=[],
                    channel_history=['sms']
                )
                
                # Run intent detection
                updated_state = intent_detector_llm(state)
                
                # Get AI response
                ai_response = updated_state.get('agent_response') or \
                             updated_state.get('conversation_thread', [])[-1] if updated_state.get('conversation_thread') else \
                             "Thank you for your message. How can I help you?"
                
                # Clean AI response (remove prefixes like "Agent:")
                if ':' in ai_response:
                    ai_response = ai_response.split(':', 1)[1].strip()
                
                print(f"🤖 AI Response: {ai_response}")
                
                # Send SMS reply
                success = await send_sms(phone_number, ai_response)
                
                if success:
                    # Save AI response
                    await db.add_conversation(
                        lead_id=lead.id,
                        message=ai_response,
                        channel='sms',
                        sender='ai',
                        intent_detected=updated_state.get('intent_detected')
                    )
                    
                    # Update lead
                    lead.last_contacted_at = datetime.now()
                    lead.response_received = True
                    await session.commit()
                    
                    print(f"✅ SMS reply sent successfully")
                else:
                    print(f"❌ Failed to send SMS reply")
                
            except Exception as e:
                print(f"❌ Error processing SMS: {e}")
                import traceback
                traceback.print_exc()
    
    async def send_sms_reply(
        self,
        phone_number: str,
        message: str,
        lead_id: int = None
    ) -> bool:
        """
        Send SMS reply and track in database
        
        Args:
            phone_number: Recipient phone number
            message: Message text
            lead_id: Optional lead ID for tracking
        
        Returns:
            Success boolean
        """
        try:
            # Send SMS
            success = await send_sms(phone_number, message)
            
            if success and lead_id:
                # Save to database
                async with AsyncSessionLocal() as session:
                    db = DBManager(session)
                    await db.add_conversation(
                        lead_id=lead_id,
                        message=message,
                        channel='sms',
                        sender='ai',
                        delivery_status='sent'
                    )
            
            return success
            
        except Exception as e:
            print(f"❌ Error sending SMS: {e}")
            return False


# Singleton instance
sms_handler = SMSHandler()