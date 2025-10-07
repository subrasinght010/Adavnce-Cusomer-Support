"""
WhatsApp Handler - Processes incoming WhatsApp webhooks from Twilio
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.context_builder import ContextBuilder
from nodes.intent_detector import intent_detector_llm
from services.whatsapp_service import send_whatsapp
from state.workflow_state import WorkflowState


class WhatsAppHandler:
    def __init__(self):
        self.processing_lock = asyncio.Lock()
    
    async def handle_incoming_whatsapp(self, webhook_data: Dict) -> Dict:
        """
        Process incoming WhatsApp message from Twilio webhook
        
        Args:
            webhook_data: Data from Twilio webhook
            {
                'From': 'whatsapp:+919876543210',
                'To': 'whatsapp:+1234567890',
                'Body': 'User message',
                'MessageSid': 'SM1234...',
                'MediaUrl0': 'https://...' (if media attached)
            }
        
        Returns:
            Response dictionary
        """
        try:
            # Extract data
            from_number = webhook_data.get('From', '').replace('whatsapp:', '').strip()
            message_body = webhook_data.get('Body', '').strip()
            message_sid = webhook_data.get('MessageSid', '')
            media_url = webhook_data.get('MediaUrl0', '')
            
            if not from_number:
                return {
                    'status': 'error',
                    'message': 'Missing sender number'
                }
            
            print(f"💬 WhatsApp received from {from_number}: {message_body}")
            
            if media_url:
                print(f"📎 Media attached: {media_url}")
            
            # Process in background
            asyncio.create_task(
                self._process_whatsapp_async(
                    from_number,
                    message_body,
                    message_sid,
                    media_url
                )
            )
            
            return {
                'status': 'success',
                'message': 'WhatsApp received and processing'
            }
            
        except Exception as e:
            print(f"❌ Error handling WhatsApp: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }
    
    async def _process_whatsapp_async(
        self,
        phone_number: str,
        message: str,
        message_sid: str,
        media_url: str = None
    ):
        """Process WhatsApp message asynchronously"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            context_builder = ContextBuilder(db)
            
            try:
                # Find or create lead
                lead = await db.get_or_create_lead(
                    phone=phone_number,
                    name=f"WhatsApp User {phone_number[-4:]}"
                )
                
                print(f"✅ Lead identified: {lead.id} - {lead.name}")
                
                # Handle media if present
                if media_url:
                    message = f"{message}\n[Media attached: {media_url}]"
                
                # Save incoming message
                metadata = {'media_url': media_url} if media_url else None
                await db.add_conversation(
                    lead_id=lead.id,
                    message=message,
                    channel='whatsapp',
                    sender='user',
                    message_id=message_sid,
                    metadata=metadata
                )
                
                # Build context
                context = await context_builder.build_context_for_ai(
                    lead_id=lead.id,
                    current_message=message,
                    channel='whatsapp',
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
                        f"User (WhatsApp): {message}"
                    ],
                    preferred_channel='whatsapp',
                    lead_status=lead.lead_status,
                    db_log=[],
                    channel_history=['whatsapp']
                )
                
                # Run intent detection
                updated_state = intent_detector_llm(state)
                
                # Get AI response
                ai_response = updated_state.get('agent_response') or \
                             updated_state.get('conversation_thread', [])[-1] if updated_state.get('conversation_thread') else \
                             "Thank you for your WhatsApp message! How can I help you?"
                
                # Clean AI response
                if ':' in ai_response:
                    ai_response = ai_response.split(':', 1)[1].strip()
                
                print(f"🤖 AI Response: {ai_response}")
                
                # Send WhatsApp reply
                success = await send_whatsapp(phone_number, ai_response)
                
                if success:
                    # Save AI response
                    await db.add_conversation(
                        lead_id=lead.id,
                        message=ai_response,
                        channel='whatsapp',
                        sender='ai',
                        intent_detected=updated_state.get('intent_detected')
                    )
                    
                    # Update lead
                    lead.last_contacted_at = datetime.now()
                    lead.response_received = True
                    await session.commit()
                    
                    print(f"✅ WhatsApp reply sent successfully")
                else:
                    print(f"❌ Failed to send WhatsApp reply")
                
            except Exception as e:
                print(f"❌ Error processing WhatsApp: {e}")
                import traceback
                traceback.print_exc()
    
    async def handle_media(self, media_url: str) -> Optional[Dict]:
        """
        Handle media attachments from WhatsApp
        
        Args:
            media_url: URL of media file
        
        Returns:
            Dictionary with media info
        """
        try:
            # Download and process media
            # This is a placeholder - implement based on your needs
            import requests
            
            response = requests.get(media_url, timeout=10)
            
            if response.status_code == 200:
                # Determine media type
                content_type = response.headers.get('Content-Type', '')
                
                media_info = {
                    'url': media_url,
                    'type': content_type,
                    'size': len(response.content)
                }
                
                # Process based on type
                if 'image' in content_type:
                    print(f"📷 Image received: {media_url}")
                elif 'pdf' in content_type:
                    print(f"📄 PDF received: {media_url}")
                elif 'audio' in content_type:
                    print(f"🎵 Audio received: {media_url}")
                
                return media_info
            
            return None
            
        except Exception as e:
            print(f"❌ Error handling media: {e}")
            return None


# Singleton instance
whatsapp_handler = WhatsAppHandler()