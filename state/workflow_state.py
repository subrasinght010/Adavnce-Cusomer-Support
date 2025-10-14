# state/workflow_state.py
"""
Workflow State with Pending Sends
"""

from typing import Dict, List, Optional, Any
from typing_extensions import TypedDict
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS
# ============================================================================

class IntentType(str, Enum):
    PRODUCT_QUERY = "product_query"
    POLICY_QUERY = "policy_query"
    PRICING_QUERY = "pricing_query"
    COMPLAINT = "complaint"
    CALLBACK_REQUEST = "callback_request"
    GENERAL_INQUIRY = "general_inquiry"
    TECHNICAL_SUPPORT = "technical_support"
    GREETING = "greeting"


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    CALL = "call"
    WEB_CHAT = "web_chat"


class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class UrgencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DirectionType(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallType(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    FOLLOW_UP = "follow_up"
    DEMO = "demo"
    CLOSING = "closing"


class ClientType(str, Enum):
    FIRST_TIME = "first_time"
    RETURNING = "returning"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    ENTERPRISE = "enterprise"
    SMB = "smb"


class LeadStage(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NURTURE = "nurture"
    CONVERTED = "converted"
    DEAD = "dead"


# ============================================================================
# STATE SCHEMA
# ============================================================================
class OptimizedWorkflowState(TypedDict):
    # Session
    session_id: str
    thread_id: str
    timestamp: str
    lead_id: str
    direction: DirectionType
    
    # Input
    current_message: str
    channel: ChannelType
    voice_file_url: Optional[str]
    
    # Lead data
    lead_data: Dict[str, Any]
    client_type: Optional[ClientType]
    conversation_history: List[Dict[str, str]]
    
    # Outbound
    call_type: Optional[CallType]
    lead_stage: Optional[LeadStage]
    lead_score: int
    approved_for_contact: bool
    approval_timestamp: Optional[str]
    approved_by: Optional[str]
    scheduled_time: Optional[str]
    attempt_count: int
    max_attempts: int
    last_attempt_timestamp: Optional[str]
    touch_sequence: List[Dict[str, Any]]
    current_touch_index: int
    next_retry_time: Optional[str]
    
    # AI processing - UPDATED
    intelligence_output: Dict[str, Any]
    detected_intent: Optional[IntentType]  # Keep for backward compatibility
    detected_intents: List[str]  # NEW: Support multiple intents
    intent_confidence: float
    extracted_entities: Dict[str, Any]  # NEW: Centralized entity storage
    sentiment: Optional[SentimentType]
    urgency: Optional[UrgencyLevel]
    
    # Execution
    communication_sent: bool
    communication_channel_used: Optional[ChannelType]
    communication_status: Optional[str]
    callback_scheduled: bool
    callback_time: Optional[str]
    data_verified: bool
    verification_issues: List[str]
    
    # Background tasks
    db_save_status: Optional[str]
    db_save_timestamp: Optional[str]
    follow_up_scheduled: bool
    follow_up_actions: List[Dict[str, Any]]
    
    # Pending sends
    pending_sends: List[Dict[str, Any]]
    
    # Routing
    is_simple_message: bool
    cache_hit: bool
    cache_key: Optional[str]
    needs_rag: bool
    needs_verification: bool
    escalate_to_human: bool
    pending_actions: List[str]
    completed_actions: List[str]
    
    # Monitoring
    node_execution_times: Dict[str, float]
    total_processing_time: float
    errors: List[Dict[str, Any]]
    retry_count: int
    llm_calls_made: int
    cache_saves_made: int


def extract_quick_fields(state: OptimizedWorkflowState) -> OptimizedWorkflowState:
    """Extract quick-access fields from intelligence_output"""
    if state.get("intelligence_output"):
        intel = state["intelligence_output"]
        
        # Handle both single and multiple intents
        intents = intel.get("intents", [])
        if not intents:
            # Fallback to old format
            single_intent = intel.get("intent")
            intents = [single_intent] if single_intent else ["general_inquiry"]
        
        state["detected_intent"] = intents[0]  # Primary intent (backward compatible)
        state["detected_intents"] = intents  # All intents (new)
        state["intent_confidence"] = intel.get("intent_confidence", 0.0)
        state["extracted_entities"] = intel.get("entities", {})  # NEW
        state["sentiment"] = intel.get("sentiment")
        state["urgency"] = intel.get("urgency")
        state["needs_rag"] = intel.get("used_knowledge_base", False)
        state["escalate_to_human"] = intel.get("requires_human", False)
        state["pending_actions"] = intel.get("next_actions", [])
    
    return state


def create_initial_state(
    lead_id: str,
    message: str,
    channel: str,
    direction: str = "inbound",
    lead_data: Dict = None,
    voice_file_url: str = None,
    call_type: str = None,
    client_type: str = None
) -> OptimizedWorkflowState:
    
    session_id = f"session_{datetime.utcnow().timestamp()}"
    thread_id = f"thread_{lead_id}"
    
    return OptimizedWorkflowState(
        session_id=session_id,
        thread_id=thread_id,
        timestamp=datetime.utcnow().isoformat(),
        lead_id=lead_id,
        direction=DirectionType(direction),
        current_message=message,
        channel=ChannelType(channel),
        voice_file_url=voice_file_url,
        lead_data=lead_data or {},
        client_type=ClientType(client_type) if client_type else None,
        conversation_history=[],
        call_type=CallType(call_type) if call_type else None,
        lead_stage=None,
        lead_score=50,
        approved_for_contact=False if direction == "outbound" else True,
        approval_timestamp=None,
        approved_by=None,
        scheduled_time=None,
        attempt_count=0,
        max_attempts=3,
        last_attempt_timestamp=None,
        touch_sequence=[],
        current_touch_index=0,
        next_retry_time=None,
        intelligence_output={},
        detected_intent=None,
        detected_intents=[],  # NEW
        intent_confidence=0.0,
        extracted_entities={},  # NEW
        sentiment=None,
        urgency=None,
        communication_sent=False,
        communication_channel_used=None,
        communication_status=None,
        callback_scheduled=False,
        callback_time=None,
        data_verified=False,
        verification_issues=[],
        db_save_status=None,
        db_save_timestamp=None,
        follow_up_scheduled=False,
        follow_up_actions=[],
        pending_sends=[],
        is_simple_message=False,
        cache_hit=False,
        cache_key=None,
        needs_rag=False,
        needs_verification=False,
        escalate_to_human=False,
        pending_actions=[],
        completed_actions=[],
        node_execution_times={},
        total_processing_time=0.0,
        errors=[],
        retry_count=0,
        llm_calls_made=0,
        cache_saves_made=0
    )