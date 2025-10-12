# nodes/outbound_intelligence_agent.py
"""
Outbound Intelligence with ReAct Agent
"""

from datetime import datetime
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate

from nodes.core.base_node import BaseNode
from nodes.core.intelligence_models import IntelligenceOutput
from state.optimized_workflow_state import OptimizedWorkflowState, extract_quick_fields
from tools.language_model import LanguageModel
from database.crud import DBManager
from database.db import get_db


OUTBOUND_REACT_PROMPT = """You are a sales agent. Use tools to gather info, then craft an appropriate outbound message.

Call Type: {call_type}
Client Type: {client_type}

TOOLS:
{tools}

Use this format:
Question: what I need to know
Thought: what to do
Action: tool name
Action Input: tool input
Observation: result
... (repeat as needed)
Thought: I have enough info
Final Answer: your sales message (natural language, not JSON)

Question: {input}
{agent_scratchpad}"""


class OutboundIntelligenceAgent(BaseNode):
    
    def __init__(self):
        super().__init__("outbound_intelligence")
        self.llm = LanguageModel()
        self.tools = self._create_tools()
    
    def _create_tools(self):
        return [
            Tool(
                name="get_lead_profile",
                description="Get lead details: score, stage, past attempts. Input: lead_id",
                func=self._get_profile
            ),
            Tool(
                name="get_past_objections",
                description="Get objections from past calls. Input: lead_id",
                func=self._get_objections
            ),
            Tool(
                name="check_company_info",
                description="Get company info for personalization. Input: company_name",
                func=lambda x: f"Company {x}: Mid-size B2B SaaS"
            )
        ]
    
    def _get_profile(self, lead_id: str) -> str:
        try:
            import asyncio
            async def _fetch():
                async with get_db() as db:
                    mgr = DBManager(db)
                    lead = await mgr.get_lead(lead_id)
                    return f"Score: {lead.lead_score}, Stage: {lead.status}, Attempts: {lead.attempt_count}" if lead else "No data"
            return asyncio.run(_fetch())
        except:
            return "Error"
    
    def _get_objections(self, lead_id: str) -> str:
        try:
            import asyncio
            async def _fetch():
                async with get_db() as db:
                    mgr = DBManager(db)
                    convos = await mgr.get_lead_conversations(lead_id, limit=10)
                    objections = [c.message for c in convos if any(word in c.message.lower() for word in ["not interested", "too expensive", "no budget"])]
                    return ", ".join(objections[:3]) if objections else "No objections recorded"
            return asyncio.run(_fetch())
        except:
            return "None"
    
    def _create_agent(self, call_type, client_type):
        prompt = PromptTemplate.from_template(OUTBOUND_REACT_PROMPT)
        agent = create_react_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=3, handle_parsing_errors=True)
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        call_type = state.get("call_type")
        client_type = state.get("client_type")
        
        agent_exec = self._create_agent(call_type, client_type)
        
        input_text = f"Generate {call_type} message for {client_type} client. Lead: {state.get('lead_id')}"
        
        try:
            result = await agent_exec.ainvoke({
                "input": input_text,
                "call_type": call_type,
                "client_type": client_type
            })
            response_text = result["output"]
            
            intelligence = IntelligenceOutput(
                intent=f"outbound_{call_type}",
                intent_confidence=0.9,
                sentiment="neutral",
                urgency="medium",
                response_text=response_text,
                next_actions=["send_response"]
            )
        except Exception as e:
            self.logger.error(f"ReAct failed: {e}")
            intelligence = IntelligenceOutput(
                intent=f"outbound_{call_type}",
                intent_confidence=0.5,
                sentiment="neutral",
                urgency="medium",
                response_text="Hi, calling from YourCompany."
            )
        
        state["intelligence_output"] = intelligence.dict()
        state = extract_quick_fields(state)
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        state["conversation_history"].append({
            "role": "assistant",
            "content": intelligence.response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return state


outbound_intelligence_agent = OutboundIntelligenceAgent()