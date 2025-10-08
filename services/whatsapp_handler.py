"""
WhatsApp Handler - Processes incoming WhatsApp webhooks from Twilio
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.context_builder import ContextBuilder
from nodes.unified_intelligence_agent import UnifiedIntelligenceAgent
from services.whatsapp_service import send_whatsapp
from state.optimized_workflow_state import OptimizedWorkflowState


class WhatsAppHandler:
    def __init__(self):
        self.processing_lock = asyncio.Lock()
        self.intelligence_agent = UnifiedIntelligenceAgent()
    
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
                print(f"📎 Media attachment: {media_url}")
            
            # Acquire lock to prevent race conditions
            async with self.processing_lock:
                async with AsyncSessionLocal() as db:
                    db_manager = DBManager(db)
                    
                    # Get or create lead
                    lead = await db_manager.get_lead_by_phone(from_number)
                    if not lead:
                        lead = await db_manager.create_lead({
                            'phone_number': from_number,
                            'channel': 'whatsapp',
                            'status': 'new',
                            'created_at': datetime.utcnow()
                        })
                    
                    lead_id = str(lead.id)
                    
                    # Save incoming message
                    message_data = {
                        'lead_id': lead_id,
                        'message': message_body,
                        'direction': 'inbound',
                        'channel': 'whatsapp',
                        'timestamp': datetime.utcnow(),
                        'message_sid': message_sid
                    }
                    
                    if media_url:
                        message_data['media_url'] = media_url
                    
                    await db_manager.create_conversation_message(message_data)
                    
                    # Build conversation history context
                    context_builder = ContextBuilder(db_manager)
                    conversation_history = await context_builder.get_conversation_context(
                        lead_id, 
                        limit=10
                    )
                    
                    # Create optimized workflow state
                    state = OptimizedWorkflowState(
                        session_id=f"whatsapp_{message_sid}",
                        lead_id=lead_id,
                        current_message=message_body,
                        channel="whatsapp",
                        conversation_history=conversation_history,
                        lead_context={
                            'phone_number': from_number,
                            'status': lead.status,
                            'previous_interactions': len(conversation_history),
                            'has_media': bool(media_url)
                        }
                    )
                    
                    # Add media URL to state if present
                    if media_url:
                        state['media_url'] = media_url
                    
                    # Process with unified intelligence agent
                    print(f"🤖 Processing with Unified Intelligence Agent...")
                    result_state = await self.intelligence_agent.execute(state)
                    
                    # Extract response from intelligence output
                    intelligence_output = result_state.get('intelligence_output', {})
                    response_text = intelligence_output.get('response_text', 
                        'Thank you for your message. Our team will get back to you shortly.')
                    
                    # Send WhatsApp response
                    whatsapp_sent = await send_whatsapp(
                        to_number=from_number,
                        message=response_text
                    )
                    
                    if whatsapp_sent:
                        # Save outbound message
                        await db_manager.create_conversation_message({
                            'lead_id': lead_id,
                            'message': response_text,
                            'direction': 'outbound',
                            'channel': 'whatsapp',
                            'timestamp': datetime.utcnow()
                        })
                        
                        # Update lead with latest intent and sentiment
                        await db_manager.update_lead(lead_id, {
                            'last_contacted': datetime.utcnow(),
                            'last_message': message_body,
                            'last_intent': intelligence_output.get('intent', 'unknown'),
                            'last_sentiment': intelligence_output.get('sentiment', 'neutral'),
                            'status': 'engaged'
                        })
                        
                        print(f"✅ WhatsApp sent successfully to {from_number}")
                    
                    return {
                        'status': 'success',
                        'lead_id': lead_id,
                        'response': response_text,
                        'intent': intelligence_output.get('intent'),
                        'sentiment': intelligence_output.get('sentiment'),
                        'has_media': bool(media_url)
                    }
        
        except Exception as e:
            print(f"❌ WhatsApp handling error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'message': str(e)
            }


# Singleton instance
whatsapp_handler = WhatsAppHandler()