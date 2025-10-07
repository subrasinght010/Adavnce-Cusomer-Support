# nodes/background_agents.py
"""
Background agents that run ASYNCHRONOUSLY
Don't block user response - run after user gets their answer

- Database Agent (saves everything)
- Follow-up Agent (schedules future actions)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from nodes.core.base_node import BaseNode, with_timing
from state.optimized_workflow_state import OptimizedWorkflowState


# ============================================================================
# 1. DATABASE AGENT (Async Persistence)
# ============================================================================

class DatabaseAgent(BaseNode):
    """
    Save everything to database
    Runs ASYNC - doesn't block user response
    """
    
    def __init__(self):
        super().__init__("database_agent")
    
    @with_timing
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
        """Save conversation to database"""
        
        conversation_record = {
            "session_id": state.get("session_id"),
            "lead_id": state.get("lead_id"),
            "timestamp": state.get("timestamp"),
            "channel": state.get("channel"),
            "user_message": state.get("current_message"),
            "bot_response": state.get("intelligence_output", {}).get("response_text"),
            "intent": state.get("detected_intent"),
            "sentiment": state.get("sentiment"),
            "conversation_history": state.get("conversation_history", [])
        }
        
        # Simulate database insert (replace with actual DB call)
        await asyncio.sleep(0.1)
        self.logger.debug(f"Conversation saved: {state.get('session_id')}")
        
        # In real app:
        # await db.conversations.insert_one(conversation_record)
        
        return True
    
    async def _save_lead_update(self, state: OptimizedWorkflowState) -> bool:
        """Update lead record"""
        
        lead_update = {
            "lead_id": state.get("lead_id"),
            "last_contacted_at": datetime.utcnow().isoformat(),
            "lead_score": state.get("lead_score"),
            "client_type": state.get("client_type"),
            "lead_data": state.get("lead_data", {}),
            "last_intent": state.get("detected_intent"),
            "last_sentiment": state.get("sentiment")
        }
        
        # Simulate database update
        await asyncio.sleep(0.08)
        self.logger.debug(f"Lead updated: {state.get('lead_id')}")
        
        # In real app:
        # await db.leads.update_one(
        #     {"lead_id": lead_id},
        #     {"$set": lead_update},
        #     upsert=True
        # )
        
        return True
    
    async def _save_metrics(self, state: OptimizedWorkflowState) -> bool:
        """Save performance metrics"""
        
        metrics_record = {
            "session_id": state.get("session_id"),
            "timestamp": datetime.utcnow().isoformat(),
            "total_processing_time_ms": state.get("total_processing_time", 0),
            "llm_calls_made": state.get("llm_calls_made", 0),
            "cache_hit": state.get("cache_hit", False),
            "node_execution_times": state.get("node_execution_times", {}),
            "errors_count": len(state.get("errors", []))
        }
        
        # Simulate analytics insert
        await asyncio.sleep(0.05)
        self.logger.debug("Metrics saved")
        
        # In real app:
        # await db.metrics.insert_one(metrics_record)
        
        return True


# ============================================================================
# 2. FOLLOW-UP AGENT (Async Scheduling)
# ============================================================================

class FollowUpAgent(BaseNode):
    """
    Schedule future follow-up actions
    Runs ASYNC - doesn't block user response
    """
    
    def __init__(self):
        super().__init__("followup_agent")
    
    @with_timing
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
                scheduled_time = await self._schedule_follow_up(follow_up)
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
        Determine what follow-ups are needed based on conversation
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
                "message": "Following up on our conversation about your needs"
            })
        
        # Pricing query but no purchase → Follow up in 3 days
        if intent == "pricing_query" and not state.get("callback_scheduled"):
            follow_ups.append({
                "action": "pricing_followup",
                "lead_id": state.get("lead_id"),
                "delay_hours": 72,
                "message": "Have you had a chance to review our pricing?"
            })
        
        # Negative sentiment → Follow up in 2 hours (urgent)
        if sentiment in ["negative", "very_negative"]:
            follow_ups.append({
                "action": "satisfaction_check",
                "lead_id": state.get("lead_id"),
                "delay_hours": 2,
                "message": "Checking in to ensure your concerns were addressed",
                "escalate": True
            })
        
        # Callback requested → Reminder before callback
        if state.get("callback_scheduled"):
            follow_ups.append({
                "action": "callback_reminder",
                "lead_id": state.get("lead_id"),
                "delay_hours": 1,  # 1 hour before callback
                "message": "Reminder: Your callback is scheduled for tomorrow"
            })
        
        # General inquiry → Nurture campaign
        if intent == "general_inquiry" and lead_score < 50:
            follow_ups.append({
                "action": "nurture_email",
                "lead_id": state.get("lead_id"),
                "delay_hours": 168,  # 1 week
                "message": "Thought you might find this resource helpful..."
            })
        
        return follow_ups
    
    async def _schedule_follow_up(self, follow_up: Dict) -> str:
        """
        Schedule a follow-up action in task queue
        """
        
        # Calculate scheduled time
        delay_hours = follow_up.get("delay_hours", 24)
        scheduled_time = datetime.utcnow() + timedelta(hours=delay_hours)
        
        # Simulate scheduling (replace with actual task queue)
        await asyncio.sleep(0.05)
        
        # In real app:
        # - Add to Celery/RQ task queue
        # - Store in database with scheduled time
        # - Set up cron job or scheduler
        
        # Example with Celery:
        # from tasks import send_followup_message
        # send_followup_message.apply_async(
        #     args=[follow_up],
        #     eta=scheduled_time
        # )
        
        return scheduled_time.isoformat()


# ============================================================================
# 3. BACKGROUND EXECUTOR (Runs both DB + Follow-up together)
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
    
    @with_timing
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
        final_state = state
        for result in results:
            if isinstance(result, dict):
                final_state.update(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Background task failed: {result}")
        
        self.logger.info("✓ Background tasks complete")
        
        return final_state


# ============================================================================
# Export instances
# ============================================================================

database_agent = DatabaseAgent()
followup_agent = FollowUpAgent()
background_executor = BackgroundExecutor()