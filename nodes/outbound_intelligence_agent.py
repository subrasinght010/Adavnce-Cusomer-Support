# langchain_agents/outbound_intelligence_agent.py
"""
Outbound Intelligence Agent - Sales/Proactive Mode
Uses LangChain for structured sales agent with tools
Handles: outbound calls, cold outreach, sales pitches, follow-ups
"""

import json
import logging
from typing import Dict, Any, List
from datetime import datetime

# LangChain imports
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import Tool

# Your existing infrastructure
from tools.language_model import LanguageModel
from state.optimized_workflow_state import OptimizedWorkflowState, extract_quick_fields, CallType, ClientType
from prompts.system_prompts import get_prompt_for_context

logger = logging.getLogger(__name__)


class OutboundIntelligenceAgent:
    """
    Outbound-specific intelligence using LangChain ReAct pattern
    Adapts tone and strategy based on call_type and client_type
    """
    
    def __init__(self):
        self.name = "outbound_intelligence"
        self.llm = LanguageModel()
        
        # Define tools for outbound agent
        self.tools = self._create_tools()
        
        logger.info("✓ Outbound Intelligence Agent initialized")
    
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for outbound agent"""
        
        return [
            Tool(
                name="get_lead_details",
                description="Get complete lead information including score, stage, past attempts. Input should be lead_id.",
                func=self._get_lead_details_sync
            ),
            Tool(
                name="check_company_info",
                description="Get company information for personalization (industry, size, tech stack). Input should be company name.",
                func=self._get_company_info_sync
            ),
            Tool(
                name="get_past_objections",
                description="Get list of objections this lead raised in past interactions. Input should be lead_id.",
                func=self._get_past_objections_sync
            )
        ]
    
    def _get_lead_details_sync(self, lead_id: str) -> str:
        """Get complete lead profile"""
        try:
            from database.crud import DBManager
            from database.db import get_db_sync
            
            with get_db_sync() as db:
                db_manager = DBManager(db)
                lead = db_manager.get_lead(lead_id)
                
                if not lead:
                    return "Lead not found"
                
                return f"""
            Lead Profile:
            - Name: {lead.name}
            - Company: {lead.company or 'Unknown'}
            - Title: {lead.title or 'Unknown'}
            - Stage: {lead.status}
            - Score: {lead.lead_score}/100
            - Last contacted: {lead.last_contact_date}
            - Total attempts: {lead.attempt_count}
            - Phone: {lead.phone}
            - Email: {lead.email}
            """
        except Exception as e:
            logger.error(f"Failed to get lead details: {e}")
            return "Could not retrieve lead details"
    
    def _get_company_info_sync(self, company_name: str) -> str:
        """Get company information for personalization"""
        # TODO: Integrate with Clearbit/ZoomInfo API
        return f"Company: {company_name} (Enrichment integration pending)"
    
    def _get_past_objections_sync(self, lead_id: str) -> str:
        """Get past objections from conversation history"""
        try:
            from database.crud import DBManager
            from database.db import get_db_sync
            
            with get_db_sync() as db:
                db_manager = DBManager(db)
                conversations = db_manager.get_lead_conversations(lead_id, limit=10)
                
                if not conversations:
                    return "No past objections recorded"
                
                # Extract objections from conversations
                objections = []
                for conv in conversations:
                    if "not interested" in conv.message.lower():
                        objections.append("Not interested")
                    elif "too expensive" in conv.message.lower():
                        objections.append("Price concern")
                    elif "no budget" in conv.message.lower():
                        objections.append("Budget constraint")
                
                return f"Past objections: {', '.join(set(objections))}" if objections else "No objections found"
        except Exception as e:
            logger.error(f"Failed to get objections: {e}")
            return "Could not retrieve objection history"
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Execute outbound intelligence with context-aware prompting"""
        
        message = state.get("current_message", "")
        conversation_history = state.get("conversation_history", [])
        lead_data = state.get("lead_data", {})
        call_type = state.get("call_type")
        client_type = state.get("client_type")
        
        logger.info(f"[OUTBOUND] Processing {call_type} call for {client_type} client...")
        
        # Select appropriate prompt based on call type
        prompt_template = get_prompt_for_context(
            direction="outbound",
            call_type=call_type.value if call_type else "cold",
            client_type=client_type.value if client_type else "professional"
        )
        
        # Prepare context
        context = {
            "user_message": message,
            "conversation_history": self._format_history(conversation_history),
            "lead_context": self._format_lead_data(lead_data, state),
            "call_objective": self._get_call_objective(call_type),
            "company_name": "YourCompany",  # From config
            "agent_name": "AI Sales Assistant"
        }
        
        # Create agent with call-specific prompt
        agent = self._create_agent(prompt_template)
        
        # Run agent
        try:
            result = await agent.ainvoke(context)
            intelligence_output = self._parse_agent_output(result, call_type)
            
        except Exception as e:
            logger.error(f"Outbound agent failed: {e}")
            intelligence_output = self._fallback_response(call_type)
        
        # Update state
        state["intelligence_output"] = intelligence_output
        state = extract_quick_fields(state)
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        
        # Add to conversation
        state["conversation_history"].append({
            "role": "assistant",
            "content": intelligence_output.get("response_text", ""),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"[OUTBOUND] Response generated for {call_type} call")
        
        return state
    
    def _create_agent(self, prompt_template: str) -> AgentExecutor:
        """Create agent with specific prompt"""
        
        prompt = PromptTemplate.from_template(prompt_template)
        
        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=3,
            handle_parsing_errors=True
        )
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history"""
        if not history:
            return "No previous conversation (first contact)"
        
        return "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in history[-5:]
        ])
    
    def _format_lead_data(self, lead_data: Dict, state: OptimizedWorkflowState) -> str:
        """Format lead data with outbound-specific info"""
        
        return f"""
Lead: {lead_data.get('name', 'Unknown')}
Company: {lead_data.get('company', 'Unknown')}
Title: {lead_data.get('title', 'Unknown')}
Industry: {lead_data.get('industry', 'Unknown')}
Lead Score: {state.get('lead_score', 50)}/100
Lead Stage: {state.get('lead_stage', 'new')}
Previous Attempts: {state.get('attempt_count', 0)}
"""
    
    def _get_call_objective(self, call_type: CallType) -> str:
        """Get objective based on call type"""
        
        objectives = {
            CallType.COLD: "Introduce company and secure 15-min discovery call",
            CallType.WARM: "Build on previous interaction and move to next stage",
            CallType.HOT: "Conduct demo and address final concerns",
            CallType.FOLLOW_UP: "Re-engage and revive interest",
            CallType.DEMO: "Demonstrate product value and use cases",
            CallType.CLOSING: "Secure verbal commitment and finalize deal"
        }
        
        return objectives.get(call_type, "Engage with lead")
    
    def _parse_agent_output(self, result: Dict, call_type: CallType) -> Dict[str, Any]:
        """Parse outbound agent output"""
        
        output = result.get("output", "")
        
        # Outbound responses are natural language, not JSON
        return {
            "intent": f"outbound_{call_type.value}",
            "intent_confidence": 0.9,
            "entities": {},
            "sentiment": "neutral",
            "urgency": "medium",
            "language_detected": "en",
            "response_text": output,
            "needs_clarification": False,
            "next_actions": ["send_response", "schedule_follow_up"],
            "requires_human": False,
            "used_knowledge_base": False,
            "rag_sources_used": []
        }
    
    def _fallback_response(self, call_type: CallType) -> Dict[str, Any]:
        """Fallback when agent fails"""
        
        fallback_messages = {
            CallType.COLD: "Hi, this is calling from YourCompany. I'd love to share how we help companies like yours. Do you have a moment?",
            CallType.WARM: "Following up on our previous conversation. I have some updates that might interest you.",
            CallType.HOT: "Ready to show you how our solution can solve your specific challenges.",
            CallType.FOLLOW_UP: "Checking back in. We've added some new features since we last spoke."
        }
        
        return {
            "intent": f"outbound_{call_type.value}",
            "intent_confidence": 0.5,
            "entities": {},
            "sentiment": "neutral",
            "urgency": "medium",
            "language_detected": "en",
            "response_text": fallback_messages.get(call_type, "Thank you for your time."),
            "needs_clarification": False,
            "next_actions": ["send_response"],
            "requires_human": False,
            "used_knowledge_base": False,
            "rag_sources_used": []
        }


# Export singleton
outbound_intelligence_agent = OutboundIntelligenceAgent()