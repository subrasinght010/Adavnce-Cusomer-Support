# langgraph_workflows/workflows.py
"""
LangGraph Workflows with Checkpointing + Human-in-Loop
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

from state.optimized_workflow_state import OptimizedWorkflowState, DirectionType
from nodes.inbound_intelligence_agent import inbound_intelligence_agent
from nodes.outbound_intelligence_agent import outbound_intelligence_agent
from nodes.lead_manager_agent import lead_manager_agent
from nodes.parallel_execution_agents import parallel_executor, communication_agent
from nodes.background_agents import background_executor

logger = logging.getLogger(__name__)


# ============================================================================
# CHECKPOINTER
# ============================================================================

checkpointer = SqliteSaver.from_conn_string("checkpoints.db")


# ============================================================================
# INBOUND WORKFLOW
# ============================================================================

def route_inbound(state: OptimizedWorkflowState) -> Literal["intelligence", "background"]:
    if state.get("is_simple_message") or state.get("cache_hit"):
        return "background"
    return "intelligence"


def build_inbound_workflow():
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", inbound_intelligence_agent.execute)
    workflow.add_node("parallel", parallel_executor.execute)
    workflow.add_node("background", background_executor.execute)
    
    workflow.set_entry_point("intelligence")
    
    workflow.add_edge("intelligence", "parallel")
    workflow.add_edge("parallel", "background")
    workflow.add_edge("background", END)
    
    return workflow.compile(checkpointer=checkpointer)


# ============================================================================
# OUTBOUND WORKFLOW with Human-in-Loop
# ============================================================================

def route_approval(state: OptimizedWorkflowState) -> Literal["execute", "END"]:
    if state.get("approved_for_contact"):
        return "execute"
    return "END"


def approval_node(state: OptimizedWorkflowState) -> OptimizedWorkflowState:
    """Human approval interrupt"""
    if not state.get("approved_for_contact"):
        interrupt("approval_required")
    return state


def build_outbound_workflow():
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("approval", approval_node)
    workflow.add_node("intelligence", outbound_intelligence_agent.execute)
    workflow.add_node("execute", communication_agent.execute)
    workflow.add_node("save", lead_manager_agent.save_to_db)
    
    workflow.set_entry_point("approval")
    
    workflow.add_conditional_edges("approval", route_approval, {
        "execute": "intelligence",
        "END": END
    })
    workflow.add_edge("intelligence", "execute")
    workflow.add_edge("execute", "save")
    workflow.add_edge("save", END)
    
    return workflow.compile(checkpointer=checkpointer)


# ============================================================================
# ROUTER
# ============================================================================

class WorkflowRouter:
    def __init__(self):
        self.inbound_workflow = build_inbound_workflow()
        self.outbound_workflow = build_outbound_workflow()
        logger.info("✓ Workflows initialized with checkpointing")
    
    async def run(self, state: OptimizedWorkflowState):
        direction = state.get("direction")
        workflow = self.inbound_workflow if direction == DirectionType.INBOUND else self.outbound_workflow
        
        config = {"configurable": {"thread_id": state.get("thread_id")}}
        
        final_state = None
        async for event in workflow.astream(state, config):
            final_state = list(event.values())[0]
        
        return final_state


workflow_router = WorkflowRouter()