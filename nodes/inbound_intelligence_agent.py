# nodes/inbound_intelligence_agent.py
"""
Inbound Intelligence with ReAct Agent
"""

import json
from datetime import datetime
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate

from nodes.core.base_node import BaseNode
from nodes.core.intelligence_models import IntelligenceOutput
from state.workflow_state import OptimizedWorkflowState, extract_quick_fields
from tools.language_model import LanguageModel
from tools.vector_store import query_knowledge_base
from database.crud import DBManager
from database.db import get_db
from prompts.system_prompts import INBOUND_REACT_PROMPT



class InboundIntelligenceAgent(BaseNode):
    
    def __init__(self):
        super().__init__("inbound_intelligence")
        self.llm = LanguageModel()
        self.tools = self._create_tools()
        self.agent = self._create_agent()
    
    def _create_tools(self):
        return [
            Tool(
                name="search_knowledge_base",
                description="Search company knowledge base for product info, policies, pricing. Input: search query",
                func=self._search_kb
            ),
            Tool(
                name="get_lead_history",
                description="Get past conversations with this lead. Input: lead_id",
                func=self._get_history
            )
        ]
    
    def _search_kb(self, query: str) -> str:
        try:
            results = query_knowledge_base(query=query, top_k=3)
            return "\n".join([f"[{r.get('metadata',{}).get('source')}]: {r.get('content')}" for r in results]) if results else "No results"
        except Exception as e:
            return f"Error: {e}"
    
    def _get_history(self, lead_id: str) -> str:
        try:
            # Sync wrapper for async DB call
            import asyncio
            async def _fetch():
                async with get_db() as db:
                    mgr = DBManager(db)
                    convos = await mgr.get_lead_conversations(lead_id, limit=5)
                    return "\n".join([f"{c.sender}: {c.message}" for c in convos]) if convos else "No history"
            return asyncio.run(_fetch())
        except:
            return "Error fetching history"
    
    def _create_agent(self):
        prompt = PromptTemplate.from_template(INBOUND_REACT_PROMPT)
        agent = create_react_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=3, handle_parsing_errors=True)
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        input_text = f"""
        User message: {state.get('current_message')}
        Lead: {state.get('lead_data',{}).get('name')}
        Channel: {state.get('channel')}
        """
        
        try:
            result = await self.agent.ainvoke({"input": input_text})
            intelligence = self._parse(result["output"])
        except Exception as e:
            self.logger.error(f"ReAct failed: {e}")
            intelligence = self._fallback()
        
        state["intelligence_output"] = intelligence.dict()
        state = extract_quick_fields(state)
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        state["conversation_history"].append({
            "role": "assistant",
            "content": intelligence.response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return state
    
    def _parse(self, text: str) -> IntelligenceOutput:
        try:
            cleaned = text.strip().replace("```json","").replace("```","")
            return IntelligenceOutput(**json.loads(cleaned))
        except:
            return self._fallback()
    
    def _fallback(self) -> IntelligenceOutput:
        return IntelligenceOutput(
            intent="general_inquiry",
            intent_confidence=0.5,
            sentiment="neutral",
            urgency="medium",
            response_text="How can I help?"
        )


inbound_intelligence_agent = InboundIntelligenceAgent()