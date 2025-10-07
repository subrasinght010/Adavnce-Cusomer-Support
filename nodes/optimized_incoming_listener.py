# nodes/optimized_incoming_listener.py
"""
Incoming Listener - Entry point with fast path optimization
Handles: Template matching, cache lookup, routing
"""

import asyncio
from typing import Optional
from nodes.core.base_node import BaseNode, with_timing
from state.optimized_workflow_state import (
    OptimizedWorkflowState,
    get_template_response,
    response_cache,
    calculate_lead_score
)


class OptimizedIncomingListener(BaseNode):
    """
    Optimized entry point with three paths:
    1. Template path (instant - 50ms)
    2. Cache path (fast - 100ms)
    3. Complex path (full processing - 1+ seconds)
    """
    
    def __init__(self):
        super().__init__("incoming_listener")
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Entry point - triage and route
        """
        
        message = state.get("current_message", "")
        
        self.logger.info(f"Processing message: {message[:50]}...")
        
        # ========== FAST PATH 1: Template Matching ==========
        template_response = await self._check_template(message)
        if template_response:
            self.logger.info("✓ Template match found (FAST PATH)")
            state["is_simple_message"] = True
            state["intelligence_output"] = {
                "response_text": template_response,
                "intent": "greeting",  # or appropriate
                "intent_confidence": 1.0,
                "next_actions": ["send_response"],
                "requires_human": False
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
    
    async def _check_template(self, message: str) -> Optional[str]:
        """
        Check if message matches a template
        Returns response if match found
        """
        # Simulate async (in case future templates are from DB)
        await asyncio.sleep(0.01)
        
        return get_template_response(message)
    
    async def _check_cache(
        self, 
        state: OptimizedWorkflowState, 
        message: str
    ) -> Optional[dict]:
        """
        Check if similar message was processed before
        Returns cached intelligence output if found
        """
        # Generate cache key
        cache_key = response_cache.generate_key(message)
        state["cache_key"] = cache_key
        
        # Check cache
        cached = response_cache.get(cache_key)
        
        if cached:
            self.logger.info(f"Cache hit for key: {cache_key[:16]}...")
            state["cache_saves_made"] = state.get("cache_saves_made", 0)
            return cached["response"]
        
        return None
    
    async def _enrich_lead_data(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Enrich lead data from various sources
        Can be extended to call external APIs (LinkedIn, Clearbit, etc.)
        """
        lead_data = state.get("lead_data", {})
        
        # Simulate enrichment (in real app, call external APIs)
        await asyncio.sleep(0.05)
        
        # Basic enrichment from message
        message = state.get("current_message", "").lower()
        
        # Detect if enterprise keywords
        enterprise_keywords = ["enterprise", "company", "business", "corporate", "team"]
        if any(keyword in message for keyword in enterprise_keywords):
            lead_data["type"] = "business"
        else:
            lead_data["type"] = "individual"
        
        state["lead_data"] = lead_data
        
        return state


# ============================================================================
# Export singleton instance
# ============================================================================

incoming_listener_node = OptimizedIncomingListener()