# graph_workflows/workflow.py
"""
LangGraph Workflows - Inbound and Outbound
"""

import logging
from langgraph.graph import StateGraph, END
from state.workflow_state import OptimizedWorkflowState, DirectionType
from nodes.inbound_agent_v2 import inbound_agent as inbound_intelligence_agent
from nodes.outbound_intelligence_agent import outbound_intelligence_agent
from nodes.message_intelligence_agent import message_intelligence_agent
from nodes.scheduler_agent import scheduler_agent
from nodes.communication_agent import communication_agent
from nodes.lead_manager_agent import lead_manager_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import asyncio

logger = logging.getLogger(__name__)

# Global checkpointer and context manager
_checkpointer = None
_checkpointer_context = None


async def get_checkpointer():
    """Initialize and keep async SQLite checkpointer context alive"""
    global _checkpointer, _checkpointer_context
    if _checkpointer is None:
        _checkpointer_context = AsyncSqliteSaver.from_conn_string("langgraph.db")
        _checkpointer = await _checkpointer_context.__aenter__()
    return _checkpointer


def build_inbound_workflow(checkpointer):
    """
    Inbound: Intelligence → Message Format → Conditional Scheduler
    """
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", inbound_intelligence_agent.execute)
    workflow.add_node("message_intelligence", message_intelligence_agent.execute)
    workflow.add_node("scheduler", scheduler_agent.execute)
    
    workflow.set_entry_point("intelligence")
    workflow.add_edge("intelligence", "message_intelligence")
    
    workflow.add_conditional_edges(
        "message_intelligence",
        should_schedule,
        {
            True: "scheduler",
            False: END
        }
    )
    workflow.add_edge("scheduler", END)
    
    return workflow.compile(checkpointer=checkpointer)


def should_schedule(state: OptimizedWorkflowState) -> bool:
    """Check if scheduling needed"""
    intelligence = state.get("intelligence_output", {})
    actions = intelligence.get("next_actions", [])
    
    schedule_triggers = [
        "schedule_callback",
        "schedule_followup",
        "delayed_send"
    ]
    
    return any(action in actions for action in schedule_triggers)


def build_outbound_workflow(checkpointer):
    """
    Outbound: Intelligence → Message Format → Communication → Scheduler
    """
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", outbound_intelligence_agent.execute)
    workflow.add_node("message_intelligence", message_intelligence_agent.execute)
    workflow.add_node("communication", communication_agent.execute)
    workflow.add_node("scheduler", scheduler_agent.execute)
    
    workflow.set_entry_point("intelligence")
    workflow.add_edge("intelligence", "message_intelligence")
    workflow.add_edge("message_intelligence", "communication")
    workflow.add_edge("communication", "scheduler")
    workflow.add_edge("scheduler", END)
    
    return workflow.compile(checkpointer=checkpointer)


class WorkflowRouter:
    """Routes to inbound or outbound workflow based on direction"""
    
    def __init__(self):
        self.inbound_workflow = None
        self.outbound_workflow = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Lazy initialize workflows with checkpointer"""
        if not self._initialized:
            checkpointer = await get_checkpointer()
            self.inbound_workflow = build_inbound_workflow(checkpointer)
            self.outbound_workflow = build_outbound_workflow(checkpointer)
            self._initialized = True
            logger.info("✓ Workflows initialized with SQLite persistence")
    
    async def run(self, state: OptimizedWorkflowState):
        """Execute workflow and save to DB"""
        await self._ensure_initialized()
        
        direction = state.get("direction")
        workflow = (
            self.inbound_workflow 
            if direction == DirectionType.INBOUND 
            else self.outbound_workflow
        )
        
        config = {"configurable": {"thread_id": f"thread_{direction}"}}
        
        final_state = None
        async for event in workflow.astream(state, config):
            final_state = list(event.values())[0]
        
        if final_state:
            await lead_manager_agent.save_to_db(final_state)
        else:
            logger.warning("Workflow completed with no final state")
        
        return final_state
    
    async def cleanup(self):
        """Cleanup checkpointer connection"""
        global _checkpointer_context
        if _checkpointer_context:
            await _checkpointer_context.__aexit__(None, None, None)


# Export singleton
workflow_router = WorkflowRouter()