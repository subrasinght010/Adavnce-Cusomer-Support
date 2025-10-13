# nodes/core/intelligence_models.py
"""
Pydantic models for intelligence outputs
"""

from typing import List, Dict
from pydantic import BaseModel, Field


class IntelligenceOutput(BaseModel):
    """Structured output from intelligence agents"""
    
    intent: str = Field(
        description="Detected intent (e.g., product_query, complaint, callback_request)"
    )
    
    intent_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for intent detection"
    )
    
    entities: Dict[str, str] = Field(
        default_factory=dict,
        description="Extracted entities (e.g., product_name, preferred_time)"
    )
    
    sentiment: str = Field(
        default="neutral",
        description="Sentiment: positive, neutral, negative"
    )
    
    urgency: str = Field(
        default="medium",
        description="Urgency level: low, medium, high, critical"
    )
    
    response_text: str = Field(
        description="Generated response message"
    )
    
    needs_clarification: bool = Field(
        default=False,
        description="Whether clarification is needed"
    )
    
    next_actions: List[str] = Field(
        default_factory=list,
        description="Actions to take (e.g., schedule_callback, send_response)"
    )
    
    requires_human: bool = Field(
        default=False,
        description="Whether human intervention is required"
    )
    
    # Optional: Add method to convert to dict (for backward compatibility)
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return self.dict()
    
    class Config:
        """Pydantic config"""
        # Allow extra fields from LLM without error
        extra = "allow"
        # Use enum values instead of enum objects
        use_enum_values = True