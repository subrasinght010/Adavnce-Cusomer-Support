# state/optimized_workflow_state.py
"""
Optimized Workflow State with clear separation of concerns
"""

from typing import Dict, List, Optional, Literal, Annotated
from typing_extensions import TypedDict
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
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
# OPTIMIZED STATE SCHEMA
# ============================================================================

class OptimizedWorkflowState(TypedDict):
    """
    Optimized state with clear separation:
    - Session info (immutable)
    - User input (set once)
    - AI processing (updated by agents)
    - Actions (execution results)
    - Metadata (monitoring)
    """
    
    # ==================== SESSION INFO (Immutable) ====================
    session_id: str
    thread_id: str
    timestamp: str
    lead_id: str
    
    # ==================== USER INPUT (Set once per message) ====================
    current_message: str
    channel: ChannelType
    voice_file_url: Optional[str]
    
    # Lead data
    lead_data: Dict[str, any]  # {name, email, phone, company, etc.}
    client_type: Optional[Literal["new", "existing"]]
    
    # Conversation context
    conversation_history: List[Dict[str, str]]  # [{role, content, timestamp}]
    
    # ==================== AI PROCESSING (Updated by agents) ====================
    
    # Intelligence output (from unified Intent + Knowledge agent)
    intelligence_output: Dict[str, any]  # Full LLM response
    """
    Structure:
    {
        "intent": IntentType,
        "intent_confidence": float,
        "entities": {...},
        "sentiment": SentimentType,
        "urgency": UrgencyLevel,
        "language_detected": str,
        "response_text": str,
        "needs_clarification": bool,
        "clarification_question": str,
        "next_actions": [str],
        "requires_human": bool,
        "rag_sources_used": [str]
    }
    """
    
    # Quick access fields (extracted from intelligence_output)
    detected_intent: Optional[IntentType]
    intent_confidence: float
    sentiment: Optional[SentimentType]
    urgency: Optional[UrgencyLevel]
    
    # ==================== EXECUTION RESULTS ====================
    
    # Communication results
    communication_sent: bool
    communication_channel_used: Optional[ChannelType]
    communication_status: Optional[str]
    
    # Scheduling results
    callback_scheduled: bool
    callback_time: Optional[str]
    
    # Verification results
    data_verified: bool
    verification_issues: List[str]
    
    # ==================== BACKGROUND TASKS ====================
    
    # Database operations (async)
    db_save_status: Optional[str]
    db_save_timestamp: Optional[str]
    
    # Follow-up scheduling (async)
    follow_up_scheduled: bool
    follow_up_actions: List[Dict[str, any]]
    
    # ==================== ROUTING & CONTROL ====================
    
    # Fast path detection
    is_simple_message: bool  # Template response used?
    cache_hit: bool  # Found in cache?
    cache_key: Optional[str]
    
    # Flow control
    needs_rag: bool
    needs_verification: bool
    escalate_to_human: bool
    
    # Next steps
    pending_actions: List[str]
    completed_actions: List[str]
    
    # ==================== MONITORING & DEBUGGING ====================
    
    # Performance tracking
    node_execution_times: Dict[str, float]  # {node_name: duration_ms}
    total_processing_time: float
    
    # Error handling
    errors: List[Dict[str, any]]  # [{node, error, timestamp}]
    retry_count: int
    
    # Metrics
    llm_calls_made: int
    cache_saves_made: int
    
    # Lead scoring (for prioritization)
    lead_score: int  # 0-100


# ============================================================================
# STATE REDUCERS (For accumulating data)
# ============================================================================

def merge_intelligence_output(
    existing: Dict[str, any], 
    new: Dict[str, any]
) -> Dict[str, any]:
    """Merge intelligence outputs, keeping most recent"""
    return new if new else existing


def append_to_list(existing: List, new: List) -> List:
    """Append new items to list"""
    return existing + new


def update_execution_times(
    existing: Dict[str, float], 
    new: Dict[str, float]
) -> Dict[str, float]:
    """Update node execution times"""
    existing.update(new)
    return existing


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_initial_state(
    lead_id: str,
    message: str,
    channel: str,
    lead_data: Dict = None,
    voice_file_url: str = None
) -> OptimizedWorkflowState:
    """Create initial state for new conversation"""
    
    session_id = f"session_{datetime.utcnow().timestamp()}"
    thread_id = f"thread_{lead_id}"
    
    return OptimizedWorkflowState(
        # Session info
        session_id=session_id,
        thread_id=thread_id,
        timestamp=datetime.utcnow().isoformat(),
        lead_id=lead_id,
        
        # User input
        current_message=message,
        channel=ChannelType(channel),
        voice_file_url=voice_file_url,
        
        # Lead data
        lead_data=lead_data or {},
        client_type=None,
        conversation_history=[],
        
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
        cache_saves_made=0,
        lead_score=50  # Default medium score
    )


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
        
        # Extract pending actions
        state["pending_actions"] = intel.get("next_actions", [])
    
    return state


# state/optimized_workflow_state.py
def calculate_lead_score(state: OptimizedWorkflowState) -> int:
    """
    Calculate lead score based on multiple factors
    Score: 0-100 (higher = better lead)
    """
    
    score = 50  # Base score
    
    lead_data = state.get("lead_data", {})
    intel = state.get("intelligence_output") or {}  # FIX: Add safety check here
    
    # Company size indicator
    if lead_data.get("company"):
        if "enterprise" in lead_data.get("company", "").lower():
            score += 15
        elif "inc" in lead_data.get("company", "").lower():
            score += 10
        else:
            score += 5
    
    # Budget mentioned
    entities = intel.get("entities", {}) if intel else {}  # FIX: Extra safety
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
        score += 10  # Ready to buy
    elif intent == IntentType.PRODUCT_QUERY:
        score += 7  # Interested
    elif intent == IntentType.CALLBACK_REQUEST:
        score += 5  # Engaged
    
    # Sentiment (positive is good)
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
    
    # Engagement (multiple messages)
    if len(state.get("conversation_history", [])) > 3:
        score += 5
    
    # Cap at 0-100
    return max(0, min(100, score))


# ============================================================================
# RESPONSE CACHE (Simple in-memory for now)
# ============================================================================

import hashlib

class ResponseCache:
    """Simple response caching"""
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
    
    def generate_key(self, message: str, intent: str = None) -> str:
        """Generate cache key from message"""
        # Normalize message
        normalized = message.lower().strip()
        
        # Create hash
        key_string = f"{normalized}_{intent or ''}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached response"""
        cached = self.cache.get(key)
        
        if cached:
            # Check if expired (1 hour TTL)
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if (datetime.utcnow() - cache_time).seconds < 3600:
                return cached
            else:
                # Expired, remove
                del self.cache[key]
        
        return None
    
    def set(self, key: str, response: Dict):
        """Cache a response"""
        self.cache[key] = {
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def clear_expired(self):
        """Clear expired cache entries"""
        now = datetime.utcnow()
        expired_keys = []
        
        for key, cached in self.cache.items():
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if (now - cache_time).seconds >= 3600:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]


# Global cache instance
response_cache = ResponseCache()


# ============================================================================
# TEMPLATE RESPONSES (For simple messages)
# ============================================================================

TEMPLATE_RESPONSES = {
    "greetings": {
        "patterns": ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"],
        "response": "Hello! How can I help you today?"
    },
    "thanks": {
        "patterns": ["thanks", "thank you", "thx", "appreciate it"],
        "response": "You're welcome! Is there anything else I can help you with?"
    },
    "goodbye": {
        "patterns": ["bye", "goodbye", "see you", "have a nice day"],
        "response": "Thank you for contacting us! Have a great day!"
    },
    "yes": {
        "patterns": ["yes", "yeah", "yep", "sure", "okay", "ok"],
        "response": "Great! Let me help you with that."
    },
    "no": {
        "patterns": ["no", "nope", "not really", "no thanks"],
        "response": "No problem! Let me know if you need anything else."
    }
}


def get_template_response(message: str) -> Optional[str]:
    """Check if message matches a template - exact match only"""
    normalized = message.lower().strip()
    
    # Skip processing long messages (substantive content)
    if len(normalized.split()) > 6:
        return None
    
    # Exact match only
    for _, template in TEMPLATE_RESPONSES.items():
        if normalized in template["patterns"]:
            return template["response"]
    
    return None