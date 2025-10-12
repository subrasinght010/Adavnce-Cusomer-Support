# state/optimized_workflow_state.py
"""
EXTENDED: Added outbound fields to existing state
Keeps all your existing inbound logic intact
"""

from typing import Dict, List, Optional, Literal, Annotated
from typing_extensions import TypedDict
from datetime import datetime
from enum import Enum


# ============================================================================
# EXISTING ENUMS (Keep as-is)
# ============================================================================

class IntentType(str, Enum):
    """All possible user intents"""
    PRODUCT_QUERY = "product_query"
    POLICY_QUERY = "policy_query"
    PRICING_QUERY = "pricing_query"
    COMPLAINT = "complaint"
    CALLBACK_REQUEST = "callback_request"
    GENERAL_INQUIRY = "general_inquiry"
    TECHNICAL_SUPPORT = "technical_support"
    GREETING = "greeting"


class ChannelType(str, Enum):
    """Communication channels"""
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    CALL = "call"
    WEB_CHAT = "web_chat"


class SentimentType(str, Enum):
    """Sentiment analysis"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class UrgencyLevel(str, Enum):
    """Urgency classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# NEW ENUMS FOR OUTBOUND
# ============================================================================

class DirectionType(str, Enum):
    """Message direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallType(str, Enum):
    """Outbound call types"""
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    FOLLOW_UP = "follow_up"
    DEMO = "demo"
    CLOSING = "closing"


class ClientType(str, Enum):
    """Client classification for tone adaptation"""
    FIRST_TIME = "first_time"
    RETURNING = "returning"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    ENTERPRISE = "enterprise"
    SMB = "smb"


class LeadStage(str, Enum):
    """Lead lifecycle stage"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NURTURE = "nurture"
    DEAD = "dead"


# ============================================================================
# EXTENDED STATE SCHEMA
# ============================================================================

class OptimizedWorkflowState(TypedDict):
    """
    EXTENDED: All your existing fields + new outbound fields
    """
    
    # ==================== SESSION INFO (Existing) ====================
    session_id: str
    thread_id: str
    timestamp: str
    lead_id: str
    
    # ==================== NEW: DIRECTION TRACKING ====================
    direction: DirectionType  # NEW: Track inbound vs outbound
    
    # ==================== USER INPUT (Existing) ====================
    current_message: str
    channel: ChannelType
    voice_file_url: Optional[str]
    
    # Lead data (existing)
    lead_data: Dict[str, any]
    client_type: Optional[ClientType]  # UPDATED: Use enum
    conversation_history: List[Dict[str, str]]
    
    # ==================== NEW: OUTBOUND SPECIFIC ====================
    
    # Outbound call configuration
    call_type: Optional[CallType]
    lead_stage: Optional[LeadStage]
    lead_score: int  # 0-100 (already exists, keep)
    
    # Approval gate
    approved_for_contact: bool
    approval_timestamp: Optional[str]
    approved_by: Optional[str]
    
    # Scheduling
    scheduled_time: Optional[str]
    attempt_count: int
    max_attempts: int
    last_attempt_timestamp: Optional[str]
    
    # Multi-touch sequence
    touch_sequence: List[Dict[str, any]]  # [{channel, time, status, result}]
    current_touch_index: int
    next_retry_time: Optional[str]
    
    # ==================== AI PROCESSING (Existing + Extended) ====================
    
    intelligence_output: Dict[str, any]
    detected_intent: Optional[IntentType]
    intent_confidence: float
    sentiment: Optional[SentimentType]
    urgency: Optional[UrgencyLevel]
    
    # ==================== EXECUTION RESULTS (Existing) ====================
    
    communication_sent: bool
    communication_channel_used: Optional[ChannelType]
    communication_status: Optional[str]
    
    callback_scheduled: bool
    callback_time: Optional[str]
    
    data_verified: bool
    verification_issues: List[str]
    
    # ==================== BACKGROUND TASKS (Existing) ====================
    
    db_save_status: Optional[str]
    db_save_timestamp: Optional[str]
    
    follow_up_scheduled: bool
    follow_up_actions: List[Dict[str, any]]
    
    # ==================== ROUTING & CONTROL (Existing) ====================
    
    is_simple_message: bool
    cache_hit: bool
    cache_key: Optional[str]
    
    needs_rag: bool
    needs_verification: bool
    escalate_to_human: bool
    
    pending_actions: List[str]
    completed_actions: List[str]
    
    # ==================== MONITORING (Existing) ====================
    
    node_execution_times: Dict[str, float]
    total_processing_time: float
    
    errors: List[Dict[str, any]]
    retry_count: int
    
    llm_calls_made: int
    cache_saves_made: int


# ============================================================================
# HELPER FUNCTIONS (Existing + Extended)
# ============================================================================

def create_initial_state(
    lead_id: str,
    message: str,
    channel: str,
    direction: str = "inbound",  # NEW parameter
    lead_data: Dict = None,
    voice_file_url: str = None,
    call_type: str = None,  # NEW parameter
    client_type: str = None  # NEW parameter
) -> OptimizedWorkflowState:
    """
    EXTENDED: Create initial state for both inbound and outbound
    """
    
    session_id = f"session_{datetime.utcnow().timestamp()}"
    thread_id = f"thread_{lead_id}"
    
    return OptimizedWorkflowState(
        # Session info
        session_id=session_id,
        thread_id=thread_id,
        timestamp=datetime.utcnow().isoformat(),
        lead_id=lead_id,
        
        # NEW: Direction
        direction=DirectionType(direction),
        
        # User input
        current_message=message,
        channel=ChannelType(channel),
        voice_file_url=voice_file_url,
        
        # Lead data
        lead_data=lead_data or {},
        client_type=ClientType(client_type) if client_type else None,
        conversation_history=[],
        
        # NEW: Outbound fields
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
        
        # AI processing
        intelligence_output={},
        detected_intent=None,
        intent_confidence=0.0,
        sentiment=None,
        urgency=None,
        
        # Execution results
        communication_sent=False,
        communication_channel_used=None,
        communication_status=None,
        callback_scheduled=False,
        callback_time=None,
        data_verified=False,
        verification_issues=[],
        
        # Background tasks
        db_save_status=None,
        db_save_timestamp=None,
        follow_up_scheduled=False,
        follow_up_actions=[],
        
        # Routing
        is_simple_message=False,
        cache_hit=False,
        cache_key=None,
        needs_rag=False,
        needs_verification=False,
        escalate_to_human=False,
        pending_actions=[],
        completed_actions=[],
        
        # Monitoring
        node_execution_times={},
        total_processing_time=0.0,
        errors=[],
        retry_count=0,
        llm_calls_made=0,
        cache_saves_made=0
    )


# Keep your existing functions
def extract_quick_fields(state: OptimizedWorkflowState) -> OptimizedWorkflowState:
    """Extract commonly used fields from intelligence_output for quick access"""
    
    if state.get("intelligence_output"):
        intel = state["intelligence_output"]
        
        state["detected_intent"] = intel.get("intent")
        state["intent_confidence"] = intel.get("intent_confidence", 0.0)
        state["sentiment"] = intel.get("sentiment")
        state["urgency"] = intel.get("urgency")
        state["needs_rag"] = intel.get("used_knowledge_base", False)
        state["escalate_to_human"] = intel.get("requires_human", False)
        state["pending_actions"] = intel.get("next_actions", [])
    
    return state


def calculate_lead_score(state: OptimizedWorkflowState) -> int:
    """
    Calculate lead score based on multiple factors
    Score: 0-100 (higher = better lead)
    KEEP YOUR EXISTING LOGIC
    """
    
    score = 50  # Base score
    
    lead_data = state.get("lead_data", {})
    intel = state.get("intelligence_output") or {}
    
    # Company size indicator
    if lead_data.get("company"):
        if "enterprise" in lead_data.get("company", "").lower():
            score += 15
        elif "inc" in lead_data.get("company", "").lower():
            score += 10
        else:
            score += 5
    
    # Budget mentioned
    entities = intel.get("entities", {}) if intel else {}
    if entities.get("budget"):
        try:
            budget = int(entities["budget"].replace("$", "").replace("k", "000"))
            if budget > 10000:
                score += 15
            elif budget > 5000:
                score += 10
            else:
                score += 5
        except:
            pass
        
    # Urgency
    urgency = state.get("urgency")
    if urgency == UrgencyLevel.CRITICAL:
        score += 10
    elif urgency == UrgencyLevel.HIGH:
        score += 7
    elif urgency == UrgencyLevel.MEDIUM:
        score += 3
    
    # Intent (buying signals)
    intent = state.get("detected_intent")
    if intent == IntentType.PRICING_QUERY:
        score += 10
    elif intent == IntentType.PRODUCT_QUERY:
        score += 7
    elif intent == IntentType.CALLBACK_REQUEST:
        score += 5
    
    # Sentiment
    sentiment = state.get("sentiment")
    if sentiment == SentimentType.POSITIVE:
        score += 5
    elif sentiment == SentimentType.VERY_NEGATIVE:
        score -= 10
    elif sentiment == SentimentType.NEGATIVE:
        score -= 5
    
    # Decision maker indicator
    if lead_data.get("title"):
        title = lead_data.get("title", "").lower()
        if any(word in title for word in ["ceo", "cto", "founder", "director"]):
            score += 15
        elif any(word in title for word in ["manager", "lead", "head"]):
            score += 10
    
    # Engagement
    if len(state.get("conversation_history", [])) > 3:
        score += 5
    
    return max(0, min(100, score))