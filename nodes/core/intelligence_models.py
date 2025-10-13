from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional

class IntelligenceOutput(BaseModel):
    """Structured output from intelligence agents"""
    
    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True
    )
    
    intent: str = Field(description="Detected intent")
    intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: Optional[Dict[str, Optional[str]]] = Field(default_factory=dict)  # Allow None values
    sentiment: str = Field(default="neutral")
    urgency: str = Field(default="medium")
    response_text: str = Field(description="Generated response")
    needs_clarification: bool = Field(default=False)
    clarification_question: Optional[str] = Field(default=None)
    next_actions: List[str] = Field(default_factory=list)
    requires_human: bool = Field(default=False)