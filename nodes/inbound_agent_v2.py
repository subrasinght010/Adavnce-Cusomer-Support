# nodes/inbound_agent_v2.py
"""
Inbound Intelligence Agent - Refactored with Multi-Intent Support
Uses base agent for ReAct loop and entity extraction
"""

from datetime import datetime
from langchain_core.tools import Tool
from nodes.core.base_intelligence_agent import BaseIntelligenceAgent
from nodes.core.intelligence_models import IntelligenceOutput
from state.workflow_state import OptimizedWorkflowState
from tools.language_model import llm
from tools.vector_store import query_knowledge_base
from database.crud import DBManager
from database.db import get_db
from prompts.robust_system_prompts import get_inbound_prompt
from prompts.response_templates import get_response
import asyncio
import json


class InboundAgent(BaseIntelligenceAgent):
    
    def __init__(self):
        super().__init__("inbound_intelligence", llm)
        self.logger.info("✓ InboundAgent initialized with multi-intent support")
    
    # ========================================================================
    # TOOL DEFINITIONS
    # ========================================================================
    
    def _create_tools(self):
        """Define inbound-specific tools"""
        self.logger.info("Initializing 9 inbound tools")
        return [
            Tool(
                name="search_knowledge_base",
                description="Search company knowledge base for product info, policies, pricing. Input: search query string",
                func=self._search_kb
            ),
            Tool(
                name="get_lead_history",
                description="Get past conversation history with lead. Input: lead_id",
                func=self._get_history
            ),
            Tool(
                name="check_ticket_status",
                description="Check support ticket status. Input: ticket_id or lead_id",
                func=self._check_ticket
            ),
            Tool(
                name="schedule_callback",
                description="Schedule callback for lead. Input: lead_id|datetime|reason (pipe-separated)",
                func=self._schedule_callback
            ),
            Tool(
                name="send_details",
                description="Queue details to be sent. Input: lead_id|channel|content_type (channel: email/sms/whatsapp)",
                func=self._send_details
            ),
            Tool(
                name="escalate_to_human",
                description="Create escalation ticket for human agent. Input: reason and urgency",
                func=self._escalate
            ),
            Tool(
                name="send_email_now",
                description="Queue email immediately. Input: email|content_type (e.g., user@test.com|pricing)",
                func=self._queue_email
            ),
            Tool(
                name="send_sms_now",
                description="Queue SMS immediately. Input: phone|content_type",
                func=self._queue_sms
            ),
            Tool(
                name="send_whatsapp_now",
                description="Queue WhatsApp message. Input: phone|content_type",
                func=self._queue_whatsapp
            )
        ]
    
    # ========================================================================
    # PROMPT GENERATION
    # ========================================================================
    
    def _get_system_prompt(self, **kwargs) -> str:
        """Generate inbound-specific system prompt"""
        return get_inbound_prompt(
            conversation_history=kwargs.get('conversation_history', ''),
            tools_description=kwargs.get('tools_description', ''),
            user_message=kwargs.get('user_message', ''),
            lead_id=kwargs.get('lead_id', ''),
            lead_name=kwargs.get('lead_name', 'Unknown'),
            channel=kwargs.get('channel', 'unknown')
        )
    
    def _extract_prompt_vars(self, state: dict) -> dict:
        """Extract variables needed for prompt from state"""
        return {
            'user_message': state.get('current_message', ''),
            'lead_id': state.get('lead_id', ''),
            'lead_name': state.get('lead_data', {}).get('name', 'Unknown'),
            'channel': state.get('channel', 'unknown')
        }
    
    # ========================================================================
    # POST-PROCESSING
    # ========================================================================
    
    def _post_process(self, intelligence: IntelligenceOutput, user_message: str, state: dict) -> IntelligenceOutput:
        """Post-process with template responses"""
        
        # Call parent post-process first
        intelligence = super()._post_process(intelligence, user_message, state)
        
        # Apply response templates for common scenarios
        try:
            if intelligence.needs_clarification and not intelligence.response_text:
                intelligence.response_text = intelligence.clarification_question or "Could you provide more details?"
            
            # Template for email send without address
            if "send_details_email" in intelligence.intents and not intelligence.entities.get("email"):
                intelligence.response_text = get_response('email_need_address')
                intelligence.needs_clarification = True
                intelligence.clarification_question = "What email address should I use?"
            
            # Template for callback without time
            elif "callback_request" in intelligence.intents and not intelligence.entities.get("callback_time"):
                intelligence.response_text = get_response('callback_need_time')
                intelligence.needs_clarification = True
                intelligence.clarification_question = "What time would you like us to call you back?"
            
        except Exception as e:
            self.logger.error(f"Template application error: {e}", exc_info=True)
        
        return intelligence
    
    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================
    
    def _search_kb(self, query: str) -> str:
        """Search knowledge base"""
        self.logger.info(f"Searching KB: {query[:50]}...")
        try:
            results = query_knowledge_base(query=query, top_k=3)
            if results:
                result_text = "\n".join([
                    f"[{r.get('metadata',{}).get('source', 'Unknown')}]: {r.get('content', '')[:200]}"
                    for r in results
                ])
                self.logger.info(f"KB returned {len(results)} results")
                return result_text
            return "No relevant information found in knowledge base."
        except Exception as e:
            self.logger.error(f"KB search error: {e}")
            return f"Error searching knowledge base: {str(e)}"
    
    def _get_history(self, lead_id: str) -> str:
        """Get lead conversation history (sync wrapper)"""
        self.logger.info(f"Fetching history for lead: {lead_id}")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._fetch_history(lead_id))
            loop.close()
            return result
        except Exception as e:
            self.logger.error(f"History fetch failed: {e}")
            return "No history available"
    
    async def _fetch_history(self, lead_id: str) -> str:
        """Async fetch history"""
        try:
            async with get_db() as db:
                mgr = DBManager(db)
                convos = await mgr.get_conversations_by_lead(lead_id, limit=5)
                if convos:
                    history = "\n".join([
                        f"[{c.timestamp}] {c.sender}: {c.message}"
                        for c in convos
                    ])
                    return f"Recent history:\n{history}"
                return "No previous conversations found"
        except Exception as e:
            self.logger.error(f"Async history fetch error: {e}")
            return f"Error: {str(e)}"
    
    def _check_ticket(self, ticket_id: str) -> str:
        """Check ticket status"""
        self.logger.info(f"Checking ticket: {ticket_id}")
        # Mock implementation - replace with real ticket system
        return f"Ticket {ticket_id}: Status = Open, Priority = Medium, Assigned to: Support Team"
    
    def _schedule_callback(self, input_str: str) -> str:
        """Schedule callback"""
        self.logger.info(f"Scheduling callback: {input_str}")
        try:
            parts = input_str.split("|")
            if len(parts) >= 3:
                lead_id, time, reason = parts[0], parts[1], parts[2]
                # TODO: Implement actual scheduling logic
                return f"Callback scheduled for lead {lead_id} at {time}. Reason: {reason}"
            return "Error: Invalid format. Use lead_id|datetime|reason"
        except Exception as e:
            self.logger.error(f"Callback scheduling error: {e}")
            return f"Error: {str(e)}"
    
    def _send_details(self, input_str: str) -> str:
        """Queue details to be sent"""
        self.logger.info(f"Sending details: {input_str}")
        try:
            parts = input_str.split("|")
            if len(parts) >= 3:
                lead_id, channel, content_type = parts[0], parts[1], parts[2]
                
                # Add to pending sends
                if not hasattr(self, '_pending_sends'):
                    self._pending_sends = []
                
                self._pending_sends.append({
                    "lead_id": lead_id,
                    "channel": channel,
                    "content_type": content_type,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return f"Details queued to send via {channel}"
            return "Error: Invalid format. Use lead_id|channel|content_type"
        except Exception as e:
            self.logger.error(f"Send details error: {e}")
            return f"Error: {str(e)}"
    
    def _escalate(self, reason: str) -> str:
        """Create escalation ticket"""
        self.logger.info(f"Escalating: {reason}")
        try:
            # TODO: Implement actual escalation logic
            ticket_id = f"ESC-{datetime.utcnow().timestamp()}"
            return f"Escalation ticket created: {ticket_id}. Reason: {reason}. Priority: High"
        except Exception as e:
            self.logger.error(f"Escalation error: {e}")
            return f"Error: {str(e)}"
    
    def _queue_email(self, input_str: str) -> str:
        """Queue email"""
        self.logger.info(f"Queueing email: {input_str}")
        try:
            parts = input_str.split("|")
            email = parts[0] if len(parts) > 0 else ""
            content_type = parts[1] if len(parts) > 1 else "general"
            
            if not hasattr(self, '_pending_sends'):
                self._pending_sends = []
            
            self._pending_sends.append({
                "channel": "email",
                "email": email,
                "content_type": content_type,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return f"Email queued to {email}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _queue_sms(self, input_str: str) -> str:
        """Queue SMS"""
        self.logger.info(f"Queueing SMS: {input_str}")
        try:
            parts = input_str.split("|")
            phone = parts[0] if len(parts) > 0 else ""
            content_type = parts[1] if len(parts) > 1 else "general"
            
            if not hasattr(self, '_pending_sends'):
                self._pending_sends = []
            
            self._pending_sends.append({
                "channel": "sms",
                "phone": phone,
                "content_type": content_type,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return f"SMS queued"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _queue_whatsapp(self, input_str: str) -> str:
        """Queue WhatsApp message"""
        self.logger.info(f"Queueing WhatsApp: {input_str}")
        try:
            parts = input_str.split("|")
            phone = parts[0] if len(parts) > 0 else ""
            content_type = parts[1] if len(parts) > 1 else "general"
            
            if not hasattr(self, '_pending_sends'):
                self._pending_sends = []
            
            self._pending_sends.append({
                "channel": "whatsapp",
                "phone": phone,
                "content_type": content_type,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return f"WhatsApp message queued"
        except Exception as e:
            return f"Error: {str(e)}"


# Export singleton
inbound_agent = InboundAgent()