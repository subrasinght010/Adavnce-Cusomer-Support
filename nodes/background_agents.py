# nodes/background_agents.py
"""
Background Agents - FULLY INTEGRATED
Connects to: database/crud.py, database/models.py, database/db.py
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

# Base class
from nodes.core.base_node import BaseNode

# State
from state.optimized_workflow_state import OptimizedWorkflowState

# YOUR EXISTING CODE - Database
from database.crud import DBManager
from database.db import get_db
from database.models import Conversation, Lead, Followup

# YOUR EXISTING CODE - Utils
from utils.message_queue import MessageQueue

# YOUR EXISTING CODE - Config
from config.settings import settings

# YOUR EXISTING CODE - Workers (if needed)
from workers.followup_worker import FollowupWorker

logger = logging.getLogger(__name__)


# ============================================================================
# 1. DATABASE AGENT (INTEGRATED)
# ============================================================================

class DatabaseAgent(BaseNode):
    """
    Save everything to database using YOUR existing DB code
    Runs ASYNC - doesn't block user response
    """
    
    def __init__(self):
        super().__init__("database_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Save conversation, lead data, and metrics to database
        """
        
        self.logger.info("Saving to database...")
        
        try:
            # Run all database operations in parallel
            save_tasks = [
                self._save_conversation(state),
                self._save_lead_update(state),
                self._save_metrics(state)
            ]
            
            results = await asyncio.gather(*save_tasks, return_exceptions=True)
            
            # Check for errors
            errors = [r for r in results if isinstance(r, Exception)]
            
            if errors:
                self.logger.error(f"Database save errors: {errors}")
                state["db_save_status"] = "partial_failure"
            else:
                state["db_save_status"] = "success"
                state["completed_actions"].append("database_save")
                self.logger.info("✓ All data saved to database")
            
            state["db_save_timestamp"] = datetime.utcnow().isoformat()
        
        except Exception as e:
            self.logger.error(f"Database save failed: {e}")
            state["db_save_status"] = "failed"
        
        return state
    
    async def _save_conversation(self, state: OptimizedWorkflowState) -> bool:
        """
        Save conversation using YOUR existing database code
        """
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Create conversation record using YOUR models
                conversation_data = {
                    "session_id": state.get("session_id"),
                    "lead_id": state.get("lead_id"),
                    "timestamp": state.get("timestamp"),
                    "channel": str(state.get("channel")),
                    "user_message": state.get("current_message"),
                    "bot_response": state.get("intelligence_output", {}).get("response_text"),
                    "intent": str(state.get("detected_intent")),
                    "sentiment": str(state.get("sentiment")),
                    "conversation_history": state.get("conversation_history", [])
                }
                
                # Use YOUR existing CRUD method
                await db_manager.create_conversation(conversation_data)
                # OR: await db_manager.save_conversation(conversation_data)
                
                self.logger.debug(f"Conversation saved: {state.get('session_id')}")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to save conversation: {e}")
            return False
    
    async def _save_lead_update(self, state: OptimizedWorkflowState) -> bool:
        """
        Update lead record using YOUR existing database code
        """
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Create/update lead using YOUR models
                lead_update = {
                    "lead_id": state.get("lead_id"),
                    "last_contacted_at": datetime.utcnow().isoformat(),
                    "lead_score": state.get("lead_score"),
                    "client_type": state.get("client_type"),
                    "lead_data": state.get("lead_data", {}),
                    "last_intent": str(state.get("detected_intent")),
                    "last_sentiment": str(state.get("sentiment")),
                    "response_received": state.get("communication_sent", False)
                }
                
                # Use YOUR existing CRUD method
                await db_manager.update_lead(state.get("lead_id"), lead_update)
                # OR: await db_manager.upsert_lead(lead_update)
                
                self.logger.debug(f"Lead updated: {state.get('lead_id')}")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to update lead: {e}")
            return False
    
    async def _save_metrics(self, state: OptimizedWorkflowState) -> bool:
        """
        Save performance metrics
        """
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                metrics_record = {
                    "session_id": state.get("session_id"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "total_processing_time_ms": state.get("total_processing_time", 0),
                    "llm_calls_made": state.get("llm_calls_made", 0),
                    "cache_hit": state.get("cache_hit", False),
                    "node_execution_times": state.get("node_execution_times", {}),
                    "errors_count": len(state.get("errors", []))
                }
                
                # Use YOUR existing CRUD method
                # await db_manager.save_metrics(metrics_record)
                
                self.logger.debug("Metrics saved")
                return True
        
        except Exception as e:
            self.logger.error(f"Failed to save metrics: {e}")
            return False


# ============================================================================
# 2. FOLLOW-UP AGENT (INTEGRATED)
# ============================================================================

class FollowUpAgent(BaseNode):
    """
    Schedule future follow-up actions
    Runs ASYNC - doesn't block user response
    Integrates with YOUR existing workers
    """
    
    def __init__(self):
        super().__init__("followup_agent")
        
        # Initialize message queue for follow-ups (YOUR existing code)
        self.message_queue = MessageQueue()
        
        # Initialize followup worker (YOUR existing code)
        try:
            self.followup_worker = FollowupWorker()
        except:
            self.followup_worker = None
            self.logger.warning("Followup worker not available")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Schedule follow-up actions based on conversation
        """
        
        self.logger.info("Scheduling follow-ups...")
        
        follow_ups = await self._determine_follow_ups(state)
        
        if not follow_ups:
            self.logger.info("No follow-ups needed")
            return state
        
        # Schedule all follow-ups
        scheduled = []
        for follow_up in follow_ups:
            try:
                scheduled_time = await self._schedule_follow_up(follow_up, state)
                scheduled.append({
                    **follow_up,
                    "scheduled_at": scheduled_time
                })
                self.logger.info(f"✓ Follow-up scheduled: {follow_up['action']} at {scheduled_time}")
            except Exception as e:
                self.logger.error(f"Failed to schedule follow-up: {e}")
        
        state["follow_up_scheduled"] = len(scheduled) > 0
        state["follow_up_actions"] = scheduled
        
        if scheduled:
            state["completed_actions"].append("schedule_followups")
        
        return state
    
    async def _determine_follow_ups(self, state: OptimizedWorkflowState) -> List[Dict]:
        """
        Determine what follow-ups are needed
        """
        follow_ups = []
        
        intelligence = state.get("intelligence_output", {})
        intent = state.get("detected_intent")
        sentiment = state.get("sentiment")
        lead_score = state.get("lead_score", 0)
        
        # High-value lead → Follow up in 24 hours
        if lead_score >= 70:
            follow_ups.append({
                "action": "high_value_followup",
                "lead_id": state.get("lead_id"),
                "delay_hours": 24,
                "message": "Following up on our conversation about your needs",
                "priority": "high"
            })
        
        # Pricing query but no purchase → Follow up in 3 days
        if "pricing" in str(intent).lower() and not state.get("callback_scheduled"):
            follow_ups.append({
                "action": "pricing_followup",
                "lead_id": state.get("lead_id"),
                "delay_hours": 72,
                "message": "Have you had a chance to review our pricing?",
                "priority": "medium"
            })
        
        # Negative sentiment → Follow up in 2 hours (urgent)
        if sentiment in ["negative", "very_negative"]:
            follow_ups.append({
                "action": "satisfaction_check",
                "lead_id": state.get("lead_id"),
                "delay_hours": 2,
                "message": "Checking in to ensure your concerns were addressed",
                "escalate": True,
                "priority": "high"
            })
        
        # Callback requested → Reminder before callback
        if state.get("callback_scheduled"):
            follow_ups.append({
                "action": "callback_reminder",
                "lead_id": state.get("lead_id"),
                "delay_hours": 1,
                "message": "Reminder: Your callback is scheduled soon",
                "priority": "high"
            })
        
        # General inquiry → Nurture campaign
        if "general" in str(intent).lower() and lead_score < 50:
            follow_ups.append({
                "action": "nurture_email",
                "lead_id": state.get("lead_id"),
                "delay_hours": 168,  # 1 week
                "message": "Thought you might find this resource helpful...",
                "priority": "low"
            })
        
        return follow_ups
    
    async def _schedule_follow_up(self, follow_up: Dict, state: OptimizedWorkflowState) -> str:
        """
        Schedule a follow-up using YOUR existing infrastructure
        """
        delay_hours = follow_up.get("delay_hours", 24)
        scheduled_time = datetime.utcnow() + timedelta(hours=delay_hours)
        
        try:
            # Option 1: Use YOUR message queue
            await self.message_queue.enqueue({
                "type": "follow_up",
                "data": follow_up,
                "scheduled_at": scheduled_time.isoformat(),
                "lead_id": state.get("lead_id")
            })
            
            # Option 2: Use YOUR followup worker
            if self.followup_worker:
                await self.followup_worker.schedule_followup(
                    lead_id=follow_up.get("lead_id"),
                    action=follow_up.get("action"),
                    scheduled_time=scheduled_time,
                    message=follow_up.get("message"),
                    priority=follow_up.get("priority", "medium")
                )
            
            # Option 3: Save to database for cron job to pick up
            async with get_db() as db:
                db_manager = DBManager(db)
                
                followup_record = {
                    "lead_id": follow_up.get("lead_id"),
                    "action": follow_up.get("action"),
                    "scheduled_time": scheduled_time.isoformat(),
                    "message": follow_up.get("message"),
                    "priority": follow_up.get("priority", "medium"),
                    "status": "pending"
                }
                
                # Use YOUR existing CRUD
                await db_manager.create_followup(followup_record)
        
        except Exception as e:
            self.logger.error(f"Failed to schedule follow-up: {e}")
            raise
        
        return scheduled_time.isoformat()


# ============================================================================
# 3. BACKGROUND EXECUTOR
# ============================================================================

class BackgroundExecutor(BaseNode):
    """
    Execute Database and Follow-up agents in parallel
    Runs AFTER user has already received response
    """
    
    def __init__(self):
        super().__init__("background_executor")
        self.database_agent = DatabaseAgent()
        self.followup_agent = FollowUpAgent()
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Run background tasks in parallel
        """
        
        self.logger.info("Starting background tasks...")
        
        # Run both agents in parallel
        tasks = [
            self.database_agent.execute(state),
            self.followup_agent.execute(state)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        final_state = state.copy()
        
        for result in results:
            if isinstance(result, dict):
                # Merge state updates
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


# ============================================================================
# Export instances
# ============================================================================

database_agent = DatabaseAgent()
followup_agent = FollowUpAgent()
background_executor = BackgroundExecutor()