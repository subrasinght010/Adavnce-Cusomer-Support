# nodes/core/intelligence_models.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class IntelligenceOutput(BaseModel):
    """Intelligence agent output model"""
    
    # Intent - support both formats
    intent: str = Field(default="general_inquiry", description="Primary intent")
    intents: List[str] = Field(default_factory=list, description="All detected intents (multi-intent)")
    intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Entities - centralized
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    
    # Metadata
    sentiment: Optional[str] = Field(default="neutral")
    urgency: Optional[str] = Field(default="medium")
    
    # Response
    response_text: str = Field(default="")
    needs_clarification: bool = Field(default=False)
    clarification_question: Optional[str] = Field(default=None)
    
    # Actions
    next_actions: List[str] = Field(default_factory=list)
    requires_human: bool = Field(default=False)
    
    # Context flags
    used_knowledge_base: bool = Field(default=False)
    conversation_complete: bool = Field(default=False)
    
    def dict(self, **kwargs):
        """Override to ensure intents list is populated"""
        data = super().dict(**kwargs)
        
        # Ensure intents list is populated
        if not data.get("intents") and data.get("intent"):
            data["intents"] = [data["intent"]]
        
        return data