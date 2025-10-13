# graph_workflows/workflow.py
"""
LangGraph Workflows - Inbound and Outbound
"""

import logging
from langgraph.graph import StateGraph, END
from utils.checkpoint import SQLiteCheckpoint

from state.workflow_state import OptimizedWorkflowState, DirectionType
from nodes.inbound_intelligence_agent import inbound_intelligence_agent
from nodes.outbound_intelligence_agent import outbound_intelligence_agent
from nodes.message_intelligence_agent import message_intelligence_agent
from nodes.scheduler_agent import scheduler_agent
from nodes.communication_agent import communication_agent
from nodes.lead_manager_agent import lead_manager_agent

logger = logging.getLogger(__name__)
checkpointer = SQLiteCheckpoint(db_path="langgraph.db")


def build_inbound_workflow():
    """
    Inbound: Intelligence → Message Format → Conditional Scheduler
    Scheduler only runs if callback/delayed action needed
    """
    workflow = StateGraph(OptimizedWorkflowState)
    
    workflow.add_node("intelligence", inbound_intelligence_agent.execute)
    workflow.add_node("message_intelligence", message_intelligence_agent.execute)
    workflow.add_node("scheduler", scheduler_agent.execute)
    
    workflow.set_entry_point("intelligence")
    workflow.add_edge("intelligence", "message_intelligence")
    
    # Conditional routing - only schedule if needed
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
    
    # Schedule only if these actions detected
    schedule_triggers = [
        "schedule_callback",
        "schedule_followup",
        "delayed_send"
    ]
    
    return any(action in actions for action in schedule_triggers)


def build_outbound_workflow():
    """
    Outbound: Intelligence → Message Format → Communication → Scheduler
    (Communication Agent sends all outbound messages)
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
        self.inbound_workflow = build_inbound_workflow()
        self.outbound_workflow = build_outbound_workflow()
        logger.info("✓ Workflows initialized")
    
    async def run(self, state: OptimizedWorkflowState):
        """Execute workflow and save to DB"""
        direction = state.get("direction")
        workflow = (
            self.inbound_workflow 
            if direction == DirectionType.INBOUND 
            else self.outbound_workflow
        )
        
        config = {"configurable": {"thread_id": state.get("thread_id")}}
        
        final_state = None
        async for event in workflow.astream(state, config):
            final_state = list(event.values())[0]
        
        # Save to database
        if final_state:
            await lead_manager_agent.save_to_db(final_state)
        else:
            logger.warning("Workflow completed with no final state")
        
        return final_state


# Export singleton
workflow_router = WorkflowRouter()