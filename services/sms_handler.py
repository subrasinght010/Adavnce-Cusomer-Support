"""
SMS Handler - Processes incoming SMS webhooks from Twilio
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.context_builder import ContextBuilder
from nodes.unified_intelligence_agent import UnifiedIntelligenceAgent
from services.sms_service import send_sms
from state.optimized_workflow_state import OptimizedWorkflowState


class SMSHandler:
    def __init__(self):
        self.processing_lock = asyncio.Lock()
        self.intelligence_agent = UnifiedIntelligenceAgent()
    
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
            
            # Acquire lock to prevent race conditions
            async with self.processing_lock:
                async with AsyncSessionLocal() as db:
                    db_manager = DBManager(db)
                    
                    # Get or create lead
                    lead = await db_manager.get_lead_by_phone(from_number)
                    if not lead:
                        lead = await db_manager.create_lead({
                            'phone_number': from_number,
                            'channel': 'sms',
                            'status': 'new',
                            'created_at': datetime.utcnow()
                        })
                    
                    lead_id = str(lead.id)
                    
                    # Save incoming message
                    await db_manager.create_conversation_message({
                        'lead_id': lead_id,
                        'message': message_body,
                        'direction': 'inbound',
                        'channel': 'sms',
                        'timestamp': datetime.utcnow(),
                        'message_sid': message_sid
                    })
                    
                    # Build conversation history context
                    context_builder = ContextBuilder(db_manager)
                    conversation_history = await context_builder.get_conversation_context(
                        lead_id, 
                        limit=10
                    )
                    
                    # Create optimized workflow state
                    state = OptimizedWorkflowState(
                        session_id=f"sms_{message_sid}",
                        lead_id=lead_id,
                        current_message=message_body,
                        channel="sms",
                        conversation_history=conversation_history,
                        lead_context={
                            'phone_number': from_number,
                            'status': lead.status,
                            'previous_interactions': len(conversation_history)
                        }
                    )
                    
                    # Process with unified intelligence agent
                    print(f"🤖 Processing with Unified Intelligence Agent...")
                    result_state = await self.intelligence_agent.execute(state)
                    
                    # Extract response from intelligence output
                    intelligence_output = result_state.get('intelligence_output', {})
                    response_text = intelligence_output.get('response_text', 
                        'Thank you for your message. Our team will get back to you shortly.')
                    
                    # Send SMS response
                    sms_sent = await send_sms(
                        to_number=from_number,
                        message=response_text
                    )
                    
                    if sms_sent:
                        # Save outbound message
                        await db_manager.create_conversation_message({
                            'lead_id': lead_id,
                            'message': response_text,
                            'direction': 'outbound',
                            'channel': 'sms',
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
                        
                        print(f"✅ SMS sent successfully to {from_number}")
                    
                    return {
                        'status': 'success',
                        'lead_id': lead_id,
                        'response': response_text,
                        'intent': intelligence_output.get('intent'),
                        'sentiment': intelligence_output.get('sentiment')
                    }
        
        except Exception as e:
            print(f"❌ SMS handling error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'message': str(e)
            }


# Singleton instance
sms_handler = SMSHandler()