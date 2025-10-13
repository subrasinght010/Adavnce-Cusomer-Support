# graph_workflows/workflow.py
"""
LangGraph Workflows - Corrected
"""

import logging
from langgraph.graph import StateGraph, END
from utils.checkpoint import SQLiteCheckpoint

from state.workflow_state import OptimizedWorkflowState, DirectionType
from nodes.inbound_intelligence_agent import inbound_intelligence_agent
from nodes.outbound_intelligence_agent import outbound_intelligence_agent
from nodes.scheduler_agent import scheduler_agent
from nodes.communication_agent import communication_agent
from nodes.lead_manager_agent import lead_manager_agent

logger = logging.getLogger(__name__)
checkpointer = SQLiteCheckpoint(db_path="langgraph.db") 

def build_inbound_workflow():
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", inbound_intelligence_agent.execute)
    workflow.add_node("communication", communication_agent.execute)
    workflow.add_node("scheduler", scheduler_agent.execute)
    
    workflow.set_entry_point("intelligence")
    workflow.add_edge("intelligence", "communication")
    workflow.add_edge("communication", "scheduler")
    workflow.add_edge("scheduler", END)
    
    return workflow.compile(checkpointer=checkpointer)


def build_outbound_workflow():
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", outbound_intelligence_agent.execute)
    workflow.add_node("communication", communication_agent.execute)
    workflow.add_node("scheduler", scheduler_agent.execute)
    
    workflow.set_entry_point("intelligence")
    workflow.add_edge("intelligence", "communication")
    workflow.add_edge("communication", "scheduler")
    workflow.add_edge("scheduler", END)
    
    return workflow.compile(checkpointer=checkpointer)


class WorkflowRouter:
    def __init__(self):
        self.inbound_workflow = build_inbound_workflow()
        self.outbound_workflow = build_outbound_workflow()
        logger.info("✓ Workflows initialized")
    
    async def run(self, state: OptimizedWorkflowState):
        direction = state.get("direction")
        workflow = self.inbound_workflow if direction == DirectionType.INBOUND else self.outbound_workflow
        
        config = {"configurable": {"thread_id": state.get("thread_id")}}
        
        final_state = None
        async for event in workflow.astream(state, config):
            final_state = list(event.values())[0]
        
        # FIXED: Add null check
        if final_state is not None:
            await lead_manager_agent.save_to_db(final_state)
        else:
            logger.warning("Workflow completed with no final state")
        
        return final_state


workflow_router = WorkflowRouter()