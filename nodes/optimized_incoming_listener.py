# nodes/optimized_incoming_listener.py
"""
Optimized Incoming Listener - Entry point with fast path
Integrates with YOUR existing: tools/stt.py, utils/audio.py, config/settings.py
"""

import asyncio
from typing import Optional
from datetime import datetime

# New base class
from nodes.core.base_node import BaseNode, with_timing

# New state
from state.optimized_workflow_state import (
    OptimizedWorkflowState,
    get_template_response,
    response_cache,
    calculate_lead_score
)

# YOUR EXISTING CODE - Integrations
from tools.stt import transcribe_with_faster_whisper  # YOUR STT
from config.settings import settings  # YOUR config

import logging
logger = logging.getLogger(__name__)


class OptimizedIncomingListener(BaseNode):
    """
    Entry point with three paths:
    1. Template path (instant - 50ms) 
    2. Cache path (fast - 100ms)
    3. Complex path (full processing - 1+ seconds)
    
    Integrates with YOUR existing audio and STT processing
    """
    
    
    def __init__(self):
        super().__init__("incoming_listener")
        from utils.audio import AudioValidator
        self.audio_validator = AudioValidator()  # YOUR audio validator
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Entry point - triage and route"""
        
        message = state.get("current_message", "")
        voice_file_url = state.get("voice_file_url")
        
        # ========== HANDLE VOICE MESSAGES ==========
        if voice_file_url:
            self.logger.info(f"🎤 Voice message detected: {voice_file_url}")
            
            try:
                # Use YOUR existing STT
                transcribed_text = await self._transcribe_voice(voice_file_url)
                
                if transcribed_text:
                    state["current_message"] = transcribed_text
                    message = transcribed_text
                    self.logger.info(f"✓ Transcribed: {message[:50]}...")
                else:
                    self.logger.error("❌ Transcription failed")
                    state["errors"].append({
                        "node": self.name,
                        "error": "Voice transcription failed",
                        "timestamp": datetime.now().isoformat()
                    })
                    return state
            
            except Exception as e:
                self.logger.error(f"❌ STT error: {e}")
                state["errors"].append({
                    "node": self.name,
                    "error": f"STT failed: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })
                return state
        
        self.logger.info(f"Processing message: {message}...")
        
        # ========== FAST PATH 1: Template Matching ==========
        template_response = await self._check_template(message)
        print("Template response:", template_response)
        if template_response:
            self.logger.info("✓ Template match found (FAST PATH)")
            state["is_simple_message"] = True
            state["intelligence_output"] = {
                "response_text": template_response,
                "intent": "greeting",
                "intent_confidence": 1.0,
                "sentiment": "neutral",
                "urgency": "low",
                "next_actions": ["send_response"],
                "requires_human": False,
                "used_knowledge_base": False
            }
            state["completed_actions"].append("template_response")
            return state
        
        # ========== FAST PATH 2: Cache Lookup ==========
        cached_response = await self._check_cache(state, message)
        if cached_response:
            self.logger.info("✓ Cache hit found (CACHE PATH)")
            state["cache_hit"] = True
            state["intelligence_output"] = cached_response
            state["completed_actions"].append("cache_hit")
            return state
        
        # ========== COMPLEX PATH: Full Processing ==========
        self.logger.info("→ Complex query, continuing to full processing")
        
        # Extract and enrich lead data
        state = await self._enrich_lead_data(state)
        
        # Calculate lead score for prioritization
        state["lead_score"] = calculate_lead_score(state)
        
        self.logger.info(f"Lead score calculated: {state['lead_score']}/100")
        
        # Add to conversation history
        state["conversation_history"].append({
            "role": "user",
            "content": message,
            "timestamp": state["timestamp"]
        })
        
        return state
    
    async def _transcribe_voice(self, voice_file_url: str) -> Optional[str]:
        """
        Transcribe voice using YOUR existing STT
        """
        try:
            # Use YOUR existing transcribe_with_faster_whisper function
            transcribed = await transcribe_with_faster_whisper(voice_file_url)
            
            # Handle different return types from your STT
            if isinstance(transcribed, dict):
                return transcribed.get("text", "")
            elif isinstance(transcribed, str):
                return transcribed
            else:
                return None
        
        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            return None
    
    async def _check_template(self, message: str) -> Optional[str]:
        """Check if message matches a template"""
        await asyncio.sleep(0.01)  # Simulate async
        return get_template_response(message)
    
    async def _check_cache(
        self, 
        state: OptimizedWorkflowState, 
        message: str
    ) -> Optional[dict]:
        """Check if similar message was processed before"""
        
        cache_key = response_cache.generate_key(message)
        state["cache_key"] = cache_key
        
        cached = response_cache.get(cache_key)
        
        if cached:
            self.logger.info(f"Cache hit for key: {cache_key[:16]}...")
            state["cache_saves_made"] = state.get("cache_saves_made", 0)
            return cached["response"]
        
        return None
    
    async def _enrich_lead_data(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Enrich lead data from various sources"""
        
        lead_data = state.get("lead_data", {})
        message = state.get("current_message", "").lower()
        
        # Basic enrichment from message
        await asyncio.sleep(0.05)
        
        # Detect if enterprise keywords
        enterprise_keywords = ["enterprise", "company", "business", "corporate", "team"]
        if any(keyword in message for keyword in enterprise_keywords):
            lead_data["type"] = "business"
        else:
            lead_data["type"] = "individual"
        
        state["lead_data"] = lead_data
        
        return state


# Export singleton instance
incoming_listener_node = OptimizedIncomingListener()