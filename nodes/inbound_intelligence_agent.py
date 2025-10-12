# langchain_agents/inbound_intelligence_agent.py
"""
Inbound Intelligence Agent - Support/Help Mode
Uses LangChain for structured agent with tools
Handles: incoming messages, support queries, reactive responses
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
from tools.vector_store import query_knowledge_base
from state.optimized_workflow_state import OptimizedWorkflowState, extract_quick_fields
from prompts.system_prompts import INBOUND_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class InboundIntelligenceAgent:
    """
    Inbound-specific intelligence using LangChain ReAct pattern
    """
    
    def __init__(self):
        self.name = "inbound_intelligence"
        self.llm = LanguageModel()
        
        # Define tools for inbound agent
        self.tools = self._create_tools()
        
        # Create LangChain agent
        self.agent = self._create_agent()
        
        logger.info("✓ Inbound Intelligence Agent initialized")
    
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for inbound agent"""
        
        return [
            Tool(
                name="search_knowledge_base",
                description="Search company knowledge base for product info, policies, pricing, etc. Input should be a search query string.",
                func=self._search_kb_sync
            ),
            Tool(
                name="check_lead_history",
                description="Get past interactions and context for current lead. Input should be lead_id.",
                func=self._get_lead_history_sync
            )
        ]
    
    def _search_kb_sync(self, query: str) -> str:
        """Synchronous wrapper for knowledge base search"""
        try:
            results = query_knowledge_base(query=query, top_k=3, relevance_threshold=0.7)
            if not results:
                return "No relevant information found in knowledge base."
            
            formatted = []
            for i, doc in enumerate(results, 1):
                source = doc.get("metadata", {}).get("source", "Unknown")
                content = doc.get("content", "")
                formatted.append(f"[{source}]: {content}")
            
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"KB search failed: {e}")
            return f"Error searching knowledge base: {str(e)}"
    
    def _get_lead_history_sync(self, lead_id: str) -> str:
        """Get lead interaction history"""
        try:
            from database.crud import DBManager
            from database.db import get_db_sync
            
            with get_db_sync() as db:
                db_manager = DBManager(db)
                lead = db_manager.get_lead(lead_id)
                
                if not lead:
                    return "No history found for this lead."
                
                return f"Lead Status: {lead.status}, Total Interactions: {lead.message_count}, Last Contact: {lead.last_contact_date}"
        except Exception as e:
            logger.error(f"Failed to get lead history: {e}")
            return "Could not retrieve lead history."
    
    def _create_agent(self) -> AgentExecutor:
        """Create LangChain ReAct agent"""
        
        prompt = PromptTemplate.from_template(INBOUND_SYSTEM_PROMPT)
        
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
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Execute inbound intelligence"""
        
        message = state.get("current_message", "")
        conversation_history = state.get("conversation_history", [])
        lead_data = state.get("lead_data", {})
        
        logger.info(f"[INBOUND] Processing support query...")
        
        # Prepare context
        context = {
            "user_message": message,
            "conversation_history": self._format_history(conversation_history),
            "lead_context": self._format_lead_data(lead_data),
            "rag_context": ""  # Will be filled by tool if needed
        }
        
        # Run agent
        try:
            result = await self.agent.ainvoke(context)
            intelligence_output = self._parse_agent_output(result)
            
        except Exception as e:
            logger.error(f"Inbound agent failed: {e}")
            intelligence_output = self._fallback_response(message)
        
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
        
        logger.info(f"[INBOUND] Intent: {intelligence_output.get('intent')}, Confidence: {intelligence_output.get('intent_confidence'):.2f}")
        
        return state
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        if not history:
            return "No previous conversation"
        
        return "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in history[-5:]
        ])
    
    def _format_lead_data(self, lead_data: Dict) -> str:
        """Format lead data for prompt"""
        if not lead_data:
            return "No lead information available"
        
        return f"""
Name: {lead_data.get('name', 'Unknown')}
Email: {lead_data.get('email', 'Not provided')}
Phone: {lead_data.get('phone', 'Not provided')}
Client Type: {lead_data.get('client_type', 'new')}
"""
    
    def _parse_agent_output(self, result: Dict) -> Dict[str, Any]:
        """Parse agent output into structured format"""
        
        output = result.get("output", "")
        
        # Try to parse as JSON
        try:
            if isinstance(output, dict):
                return output
            
            # Clean and parse
            cleaned = output.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:-3]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:-3]
            
            parsed = json.loads(cleaned)
            return parsed
        
        except json.JSONDecodeError:
            # Fallback: extract text response
            return {
                "intent": "general_inquiry",
                "intent_confidence": 0.7,
                "entities": {},
                "sentiment": "neutral",
                "urgency": "medium",
                "language_detected": "en",
                "response_text": output,
                "needs_clarification": False,
                "next_actions": ["send_response"],
                "requires_human": False,
                "used_knowledge_base": False,
                "rag_sources_used": []
            }
    
    def _fallback_response(self, message: str) -> Dict[str, Any]:
        """Fallback response when agent fails"""
        return {
            "intent": "general_inquiry",
            "intent_confidence": 0.5,
            "entities": {},
            "sentiment": "neutral",
            "urgency": "medium",
            "language_detected": "en",
            "response_text": "I'm having trouble processing your request. Let me connect you with a specialist.",
            "needs_clarification": True,
            "next_actions": ["escalate_to_human"],
            "requires_human": True,
            "used_knowledge_base": False,
            "rag_sources_used": []
        }


# Export singleton
inbound_intelligence_agent = InboundIntelligenceAgent()