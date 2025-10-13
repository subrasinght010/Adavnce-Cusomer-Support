# nodes/inbound_intelligence_agent.py
"""
Inbound Intelligence with ReAct Agent - FIXED
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
                func=self._get_history_sync  # FIXED: Use sync wrapper
            )
        ]
    
    def _search_kb(self, query: str) -> str:
        """Synchronous KB search"""
        try:
            results = query_knowledge_base(query=query, top_k=3)
            return "\n".join([f"[{r.get('metadata',{}).get('source')}]: {r.get('content')}" for r in results]) if results else "No results"
        except Exception as e:
            self.logger.error(f"KB search failed: {e}")
            return f"Error: {e}"
    
    def _get_history_sync(self, lead_id: str) -> str:
        """FIXED: Proper sync wrapper for async DB call"""
        try:
            # Get or create event loop safely
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No loop running, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._get_history_async(lead_id))
                loop.close()
                return result
            else:
                # Loop already running - use run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_in_new_loop, lead_id)
                    return future.result(timeout=10)
        except Exception as e:
            self.logger.error(f"History fetch failed: {e}")
            return "Error fetching history"
    
    def _run_in_new_loop(self, lead_id: str) -> str:
        """Run async function in new event loop (for nested calls)"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._get_history_async(lead_id))
        finally:
            loop.close()
    
    async def _get_history_async(self, lead_id: str) -> str:
        """Actual async DB fetch"""
        try:
            async with get_db() as db:
                mgr = DBManager(db)
                convos = await mgr.get_lead_conversations(lead_id, limit=5)
                return "\n".join([f"{c.sender}: {c.message}" for c in convos]) if convos else "No history"
        except Exception as e:
            self.logger.error(f"DB fetch error: {e}")
            return "No history"
    
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
        except Exception as e:
            self.logger.warning(f"Parse failed: {e}")
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