"""Inbound Intelligence Agent - Refactored"""
from langchain_core.tools import Tool
from nodes.core.base_intelligence_agent import BaseIntelligenceAgent
from nodes.core.intelligence_models import IntelligenceOutput
from tools.language_model import llm
from tools.vector_store import query_knowledge_base
from database.crud import DBManager
from database.db import get_db
from prompts.robust_system_prompts import get_inbound_prompt
from prompts.response_templates import get_response


class InboundAgent(BaseIntelligenceAgent):
    
    def __init__(self):
        super().__init__("inbound_intelligence", llm)
    
    def _create_tools(self):
        return [
            Tool(name="search_knowledge_base", description="Search KB for product/policy info. Input: query", func=self._search_kb),
            Tool(name="get_lead_history", description="Get past conversations. Input: lead_id", func=self._get_history),
            Tool(name="check_ticket_status", description="Check ticket status. Input: ticket_id", func=self._check_ticket),
            Tool(name="schedule_callback", description="Schedule callback. Input: lead_id|datetime|reason", func=self._schedule_callback),
            Tool(name="send_details", description="Send details. Input: lead_id|channel|content_type", func=self._send_details),
            Tool(name="escalate_to_human", description="Escalate to human. Input: reason", func=self._escalate),
        ]
    
    def _get_system_prompt(self, **kwargs) -> str:
        return get_inbound_prompt(**kwargs)
    
    def _extract_prompt_vars(self, state: dict) -> dict:
        return {
            'user_message': state.get('current_message'),
            'lead_name': state.get('lead_data', {}).get('name', 'Unknown'),
            'lead_id': state.get('lead_id', 'unknown'),
            'channel': state.get('channel', 'unknown'),
        }
    
    def _validate_entities(self, intelligence: IntelligenceOutput, user_message: str) -> IntelligenceOutput:
        """Validate and clear hallucinated entities"""
        entities = intelligence.entities or {}
        
        # Callback without time
        if 'callback' in intelligence.intent.lower():
            time_keywords = ['at', 'pm', 'am', ':00']
            if not any(k in user_message.lower() for k in time_keywords) and entities.get('callback_time'):
                entities['callback_time'] = None
                intelligence.needs_clarification = True
                intelligence.clarification_question = "What time works best?"
                intelligence.response_text = "What time works best for your callback?"
                intelligence.next_actions = []
        
        # Email without address
        if 'email' in intelligence.intent.lower() and entities.get('email') and '@' not in user_message:
            entities['email'] = None
        
        # Phone without digits
        if entities.get('phone') and not any(c.isdigit() for c in user_message):
            entities['phone'] = None
        
        intelligence.entities = entities
        return intelligence
    
    def _apply_response_template(self, intelligence: IntelligenceOutput, state: dict) -> IntelligenceOutput:
        """Apply response templates - safe entity access"""
        try:
            intent = intelligence.intent.lower()
            entities = intelligence.entities or {}
            lead = state.get('lead_data', {})
            
            # Callback
            if 'callback' in intent:
                if entities.get('callback_time'):
                    intelligence.response_text = get_response('callback_scheduled', 
                        time=entities['callback_time'], name=lead.get('name', 'Our team'), phone=lead.get('phone', 'your number'))
                else:
                    intelligence.response_text = get_response('callback_need_time')
            
            # Email
            elif 'email' in intent:
                if entities.get('email'):
                    intelligence.response_text = get_response('email_sent', 
                        content_type=entities.get('content_type', 'info'), email=entities['email'])
                else:
                    intelligence.response_text = get_response('email_need_address')
            
            # Clarification
            elif intelligence.needs_clarification:
                intelligence.response_text = get_response('clarification', 
                    question=intelligence.clarification_question or 'what you need')
        
        except Exception as e:
            self.logger.error(f"Template error: {e}")
        
        return intelligence
    
    # Tool implementations
    def _search_kb(self, query: str) -> str:
        try:
            results = query_knowledge_base(query=query, top_k=3)
            return "\n".join([f"[{r.get('metadata',{}).get('source')}]: {r.get('content')}" for r in results]) if results else "No results"
        except Exception as e:
            return f"Error: {e}"
    
    def _get_history(self, lead_id: str) -> str:
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._fetch_history(lead_id))
            loop.close()
            return result
        except:
            return "No history"
    
    async def _fetch_history(self, lead_id: str) -> str:
        try:
            async with get_db() as db:
                mgr = DBManager(db)
                convos = await mgr.get_lead_conversations(lead_id, limit=5)
                return "\n".join([f"{c.sender}: {c.message}" for c in convos]) if convos else "No history"
        except:
            return "Error"
    
    def _check_ticket(self, ticket_id: str) -> str:
        return f"Ticket {ticket_id}: No open tickets"
    
    def _schedule_callback(self, input_str: str) -> str:
        parts = input_str.split('|')
        if len(parts) < 2 or not parts[1]:
            return "ERROR: Time required"
        self.logger.info(f"Callback: {input_str}")
        return f"Callback scheduled for {parts[1]}"
    
    def _send_details(self, input_str: str) -> str:
        parts = input_str.split('|')
        if len(parts) < 3:
            return "ERROR: Missing channel/content"
        self.logger.info(f"Send: {input_str}")
        return f"{parts[2]} sent via {parts[1]}"
    
    def _escalate(self, reason: str) -> str:
        return f"Escalated: {reason}"


inbound_agent = InboundAgent()