# nodes/background_agents.py
"""
Background Agents - UPDATED for Inbound/Outbound
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict

from nodes.core.base_node import BaseNode
from state.optimized_workflow_state import OptimizedWorkflowState, DirectionType
from database.crud import DBManager
from database.db import get_db

logger = logging.getLogger(__name__)


# ============================================================================
# 1. DATABASE AGENT (UPDATED)
# ============================================================================

class DatabaseAgent(BaseNode):
    """Save to database - handles both inbound and outbound"""
    
    def __init__(self):
        super().__init__("database_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Save conversation and lead updates"""
        
        self.logger.info("Saving to database...")
        
        try:
            save_tasks = [
                self._save_conversation(state),
                self._save_lead_update(state)
            ]
            
            results = await asyncio.gather(*save_tasks, return_exceptions=True)
            
            errors = [r for r in results if isinstance(r, Exception)]
            
            if errors:
                self.logger.error(f"DB save errors: {errors}")
                state["db_save_status"] = "partial_failure"
            else:
                state["db_save_status"] = "success"
                state["completed_actions"].append("database_save")
                self.logger.info("✓ Data saved")
            
            state["db_save_timestamp"] = datetime.utcnow().isoformat()
        
        except Exception as e:
            self.logger.error(f"DB save failed: {e}")
            state["db_save_status"] = "failed"
        
        return state
    
    async def _save_conversation(self, state: OptimizedWorkflowState) -> bool:
        """Save conversation record"""
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                conversation = {
                    "lead_id": state.get("lead_id"),
                    "session_id": state.get("session_id"),
                    "direction": state.get("direction"),  # NEW: inbound/outbound
                    "channel": str(state.get("channel")),
                    "message": state.get("current_message"),
                    "response": state.get("intelligence_output", {}).get("response_text"),
                    "intent": str(state.get("detected_intent")),
                    "sentiment": str(state.get("sentiment")),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await db_manager.save_conversation(conversation)
                self.logger.debug("Conversation saved")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to save conversation: {e}")
            return False
    
    async def _save_lead_update(self, state: OptimizedWorkflowState) -> bool:
        """Save lead updates - different fields for inbound vs outbound"""
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                direction = state.get("direction")
                
                # Common fields
                lead_update = {
                    "last_contact_date": datetime.utcnow().isoformat(),
                    "lead_score": state.get("lead_score"),
                    "last_intent": str(state.get("detected_intent")),
                    "last_sentiment": str(state.get("sentiment"))
                }
                
                # Outbound-specific fields
                if direction == DirectionType.OUTBOUND:
                    lead_update.update({
                        "status": str(state.get("lead_stage")),  # NEW
                        "attempt_count": state.get("attempt_count", 0),  # NEW
                        "last_call_type": str(state.get("call_type")),  # NEW
                        "last_attempt_timestamp": datetime.utcnow().isoformat()  # NEW
                    })
                
                # Inbound-specific
                else:
                    lead_update.update({
                        "response_received": state.get("communication_sent", False)
                    })
                
                await db_manager.update_lead(state.get("lead_id"), lead_update)
                self.logger.debug(f"Lead updated: {state.get('lead_id')}")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to update lead: {e}")
            return False


# ============================================================================
# 2. FOLLOW-UP AGENT
# ============================================================================

class FollowUpAgent(BaseNode):
    """Schedule follow-up actions"""
    
    def __init__(self):
        super().__init__("followup_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Schedule follow-ups based on conversation"""
        
        self.logger.info("Scheduling follow-ups...")
        
        follow_ups = await self._determine_follow_ups(state)
        
        if not follow_ups:
            self.logger.info("No follow-ups needed")
            return state
        
        try:
            for followup in follow_ups:
                await self._schedule_followup(followup)
            
            state["follow_up_scheduled"] = True
            state["follow_up_actions"] = follow_ups
            state["completed_actions"].append("schedule_followups")
            
            self.logger.info(f"✓ {len(follow_ups)} follow-ups scheduled")
        
        except Exception as e:
            self.logger.error(f"Follow-up scheduling failed: {e}")
            state["follow_up_scheduled"] = False
        
        return state
    
    async def _determine_follow_ups(self, state: OptimizedWorkflowState):
        """Determine what follow-ups are needed"""
        
        intelligence = state.get("intelligence_output", {})
        next_actions = intelligence.get("next_actions", [])
        direction = state.get("direction")
        
        follow_ups = []
        
        # Inbound follow-ups
        if direction == DirectionType.INBOUND:
            if "send_email" in next_actions:
                follow_ups.append({
                    "action": "send_email",
                    "lead_id": state.get("lead_id"),
                    "delay_hours": 1,
                    "priority": "medium"
                })
        
        # Outbound follow-ups
        else:
            if not state.get("communication_sent"):
                # Retry if failed
                follow_ups.append({
                    "action": "retry_contact",
                    "lead_id": state.get("lead_id"),
                    "delay_hours": 24,
                    "priority": "high"
                })
        
        return follow_ups
    
    async def _schedule_followup(self, followup: Dict):
        """Schedule a follow-up action"""
        try:
            scheduled_time = datetime.utcnow() + timedelta(hours=followup.get("delay_hours", 24))
            
            async with get_db() as db:
                db_manager = DBManager(db)
                
                record = {
                    "lead_id": followup.get("lead_id"),
                    "action": followup.get("action"),
                    "scheduled_time": scheduled_time.isoformat(),
                    "priority": followup.get("priority", "medium"),
                    "status": "pending"
                }
                
                await db_manager.create_followup(record)
        
        except Exception as e:
            self.logger.error(f"Failed to schedule follow-up: {e}")


# ============================================================================
# 3. BACKGROUND EXECUTOR
# ============================================================================

class BackgroundExecutor(BaseNode):
    """Execute DB and Follow-up in parallel"""
    
    def __init__(self):
        super().__init__("background_executor")
        self.database_agent = DatabaseAgent()
        self.followup_agent = FollowUpAgent()
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Run background tasks"""
        
        self.logger.info("Starting background tasks...")
        
        tasks = [
            self.database_agent.execute(state),
            self.followup_agent.execute(state)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_state = state.copy()
        
        for result in results:
            if isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, list) and key in final_state:
                        if key == "completed_actions":
                            final_state[key] = list(set(final_state[key] + value))
                        elif key == "errors":
                            final_state[key].extend(value)
                        else:
                            final_state[key] = value
                    else:
                        final_state[key] = value
            
            elif isinstance(result, Exception):
                self.logger.error(f"Background task failed: {result}")
                if "errors" not in final_state:
                    final_state["errors"] = []
                final_state["errors"].append({
                    "node": "background_executor",
                    "error": str(result)
                })
        
        self.logger.info("✓ Background tasks complete")
        
        return final_state


# Export
database_agent = DatabaseAgent()
followup_agent = FollowUpAgent()
background_executor = BackgroundExecutor()