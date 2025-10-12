# langgraph_workflows/workflows.py
"""
Separate Inbound and Outbound LangGraph Workflows
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state.optimized_workflow_state import OptimizedWorkflowState, DirectionType
from langchain_agents.inbound_intelligence_agent import inbound_intelligence_agent
from langchain_agents.outbound_intelligence_agent import outbound_intelligence_agent
from langchain_agents.lead_manager_agent import lead_manager_agent
from nodes.parallel_execution_agents import parallel_executor, communication_agent
from nodes.optimized_incoming_listener import incoming_listener_node

logger = logging.getLogger(__name__)


# ============================================================================
# INBOUND WORKFLOW (Event-Driven)
# ============================================================================

def route_inbound(state: OptimizedWorkflowState) -> Literal["intelligence", "background"]:
    """Route inbound after fast-path check"""
    if state.get("is_simple_message") or state.get("cache_hit"):
        return "background"
    return "intelligence"


def build_inbound_workflow():
    """Inbound: Webhook → Listener → Intelligence → Response"""
    
    workflow = StateGraph(OptimizedWorkflowState)
    
    # Nodes
    workflow.add_node("listener", incoming_listener_node)
    workflow.add_node("intelligence", inbound_intelligence_agent.execute)
    workflow.add_node("communication", communication_agent.execute)
    workflow.add_node("background", lead_manager_agent.save_to_db)
    
    # Flow
    workflow.set_entry_point("listener")
    workflow.add_conditional_edges("listener", route_inbound, {
        "intelligence": "intelligence",
        "background": "background"
    })
    workflow.add_edge("intelligence", "communication")
    workflow.add_edge("communication", "background")
    workflow.add_edge("background", END)
    
    return workflow.compile(checkpointer=MemorySaver())


# ============================================================================
# OUTBOUND WORKFLOW (Schedule-Driven)
# ============================================================================

def route_outbound(state: OptimizedWorkflowState) -> Literal["execute", "END"]:
    """Check if approved"""
    if state.get("approved_for_contact"):
        return "execute"
    return "END"


def build_outbound_workflow():
    """Outbound: Lead Manager → Approval → Outbound Intelligence → Execute"""
    
    workflow = StateGraph(OptimizedWorkflowState)
    
    # Nodes
    workflow.add_node("approval_check", lambda s: s)  # Placeholder, approval happens in Lead Manager
    workflow.add_node("intelligence", outbound_intelligence_agent.execute)
    workflow.add_node("execute", communication_agent.execute)
    workflow.add_node("save", lead_manager_agent.save_to_db)
    
    # Flow
    workflow.set_entry_point("approval_check")
    workflow.add_conditional_edges("approval_check", route_outbound, {
        "execute": "intelligence",
        "END": END
    })
    workflow.add_edge("intelligence", "execute")
    workflow.add_edge("execute", "save")
    workflow.add_edge("save", END)
    
    return workflow.compile(checkpointer=MemorySaver())


# ============================================================================
# WORKFLOW RUNNERS
# ============================================================================

class WorkflowRouter:
    """Routes to correct workflow based on direction"""
    
    def __init__(self):
        self.inbound_workflow = build_inbound_workflow()
        self.outbound_workflow = build_outbound_workflow()
        logger.info("✓ Workflows initialized (Inbound + Outbound)")
    
    async def run(self, state: OptimizedWorkflowState):
        """Run appropriate workflow"""
        direction = state.get("direction")
        
        if direction == DirectionType.INBOUND:
            logger.info("[INBOUND WORKFLOW] Starting...")
            return await self._run_workflow(self.inbound_workflow, state)
        else:
            logger.info("[OUTBOUND WORKFLOW] Starting...")
            return await self._run_workflow(self.outbound_workflow, state)
    
    async def _run_workflow(self, workflow, state):
        """Execute workflow"""
        config = {"configurable": {"thread_id": state.get("thread_id")}}
        
        final_state = None
        async for event in workflow.astream(state, config):
            final_state = list(event.values())[0]
        
        return final_state


# Export singleton
workflow_router = WorkflowRouter()