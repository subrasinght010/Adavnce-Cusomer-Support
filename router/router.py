# router/router.py

from fastapi import APIRouter, Request
from pydantic import BaseModel
from state.workflow_state import WorkflowState
from nodes.incoming_listener import incoming_listener
from graph_builder import graph  # Your LangGraph graph instance

router = APIRouter()

# -----------------------------
# Request schema
# -----------------------------
class IncomingMessage(BaseModel):
    lead_id: str
    message: str = None      # optional if voice
    channel: str             # "whatsapp", "email", "call", "voice"
    voice_file_url: str = None  # optional, if voice call

# -----------------------------
# Webhook endpoint
# -----------------------------
@router.post("/webhook/incoming")
async def handle_incoming_message(msg: IncomingMessage):
    """
    Handles incoming messages or voice calls.
    Updates WorkflowState and triggers LangGraph workflow.
    """
    # 1. Prepare message_data dict
    message_data = msg.dict()

    # 2. Get current workflow state (or create new)
    state = WorkflowState()  # Or fetch from DB if persisting per lead

    # 3. Run incoming_listener node
    updated_state = incoming_listener(state, message_data)

    # 4. Optionally run graph from this state
    graph.state = updated_state
    graph.run(start_node="incoming_listener")

    return {
        "status": "success",
        "lead_id": msg.lead_id,
        "pending_action": updated_state.pending_action,
        "conversation_thread": updated_state.conversation_thread
    }
