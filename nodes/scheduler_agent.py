# nodes/scheduler_agent.py
"""
Scheduler Agent - Deterministic scheduling without LLM
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from dateutil import parser

from nodes.core.base_node import BaseNode
from state.optimized_workflow_state import OptimizedWorkflowState
from database.crud import DBManager
from database.db import get_db


class SchedulerAgent(BaseNode):
    """Handles all call scheduling (urgent + non-urgent)"""
    
    def __init__(self):
        super().__init__("scheduler_agent")
        self.urgent_threshold_minutes = 30
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Real-time callback scheduling from Intelligence Agent"""
        
        intelligence = state.get("intelligence_output", {})
        next_actions = intelligence.get("next_actions", [])
        
        if "schedule_callback" not in next_actions:
            return state
        
        self.logger.info("Processing callback request...")
        
        try:
            entities = intelligence.get("entities", {})
            preferred_time = entities.get("preferred_time")
            
            # Parse time
            scheduled_time = self._parse_time(preferred_time)
            
            # Check conflicts and adjust if needed
            scheduled_time = await self._check_and_resolve_conflicts(
                state.get("lead_id"),
                scheduled_time
            )
            
            # Save to DB
            await self._save_to_db(
                lead_id=state.get("lead_id"),
                scheduled_time=scheduled_time,
                call_type="callback",
                channel=state.get("channel"),
                priority="high"
            )
            
            # Create urgent task if <30 min
            if self._is_urgent(scheduled_time):
                asyncio.create_task(
                    self._execute_urgent_callback(
                        state.get("lead_id"),
                        scheduled_time
                    )
                )
            
            state["callback_scheduled"] = True
            state["callback_time"] = scheduled_time.isoformat()
            state["completed_actions"].append("schedule_callback")
            
            self.logger.info(f"✓ Callback scheduled: {scheduled_time}")
            
        except Exception as e:
            self.logger.error(f"Scheduling failed: {e}")
            state["callback_scheduled"] = False
        
        return state
    
    async def schedule_from_lead_manager(
        self,
        lead_id: str,
        call_type: str,
        client_type: str = None,
        scheduled_time: Optional[datetime] = None,
        channel: str = "call",
        priority: str = "medium"
    ) -> datetime:
        """Entry point for Lead Manager batch scheduling"""
        
        self.logger.info(f"Batch scheduling {call_type} for lead {lead_id}")
        
        # Calculate time if not provided
        if not scheduled_time:
            scheduled_time = self._calculate_optimal_time(call_type, priority)
        
        # Check conflicts
        scheduled_time = await self._check_and_resolve_conflicts(
            lead_id,
            scheduled_time
        )
        
        # Save to DB
        await self._save_to_db(
            lead_id=lead_id,
            scheduled_time=scheduled_time,
            call_type=call_type,
            channel=channel,
            priority=priority
        )
        
        # Create urgent task if needed
        if self._is_urgent(scheduled_time):
            asyncio.create_task(
                self._execute_urgent_callback(lead_id, scheduled_time)
            )
        
        return scheduled_time
    
    def _parse_time(self, time_str: Optional[str]) -> datetime:
        """Parse natural language time to datetime"""
        
        if not time_str:
            return datetime.utcnow() + timedelta(hours=24)
        
        time_str_lower = time_str.lower().strip()
        now = datetime.utcnow()
        
        # Minutes: "in 5 minutes", "5 min"
        if "minute" in time_str_lower or "min" in time_str_lower:
            minutes = int(''.join(filter(str.isdigit, time_str_lower)) or 30)
            return now + timedelta(minutes=minutes)
        
        # Hours: "in 2 hours", "2 hr"
        if "hour" in time_str_lower or "hr" in time_str_lower:
            hours = int(''.join(filter(str.isdigit, time_str_lower)) or 2)
            return now + timedelta(hours=hours)
        
        # Tomorrow: "tomorrow", "tomorrow at 3pm"
        if "tomorrow" in time_str_lower:
            tomorrow = now + timedelta(days=1)
            try:
                parsed = parser.parse(time_str_lower)
                return tomorrow.replace(hour=parsed.hour, minute=parsed.minute)
            except:
                return tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Next week
        if "next week" in time_str_lower:
            return now + timedelta(days=7)
        
        # Today: "at 3pm", "3:30 PM"
        if "today" in time_str_lower or "pm" in time_str_lower or "am" in time_str_lower:
            try:
                parsed = parser.parse(time_str_lower)
                return now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            except:
                pass
        
        # Try direct parsing
        try:
            return parser.parse(time_str)
        except:
            # Default: 24 hours from now
            return now + timedelta(hours=24)
    
    def _is_urgent(self, scheduled_time: datetime) -> bool:
        """Check if callback is urgent (<30 min)"""
        delta_minutes = (scheduled_time - datetime.utcnow()).total_seconds() / 60
        return 0 < delta_minutes <= self.urgent_threshold_minutes
    
    def _calculate_optimal_time(
        self,
        call_type: str,
        priority: str
    ) -> datetime:
        """Calculate optimal contact time"""
        
        now = datetime.utcnow()
        hour = now.hour
        
        # Business hours: 9 AM - 6 PM
        if 9 <= hour < 16:
            # During business hours
            if priority == "high":
                return now + timedelta(hours=1)
            return now + timedelta(hours=2)
        
        # Outside business hours - schedule for next day 10 AM
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    
    async def _check_and_resolve_conflicts(
        self,
        lead_id: str,
        scheduled_time: datetime
    ) -> datetime:
        """Check for scheduling conflicts and resolve"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Check ±15 minute window
                conflicts = await db_manager.get_scheduled_calls_for_lead(
                    lead_id,
                    start_time=scheduled_time - timedelta(minutes=15),
                    end_time=scheduled_time + timedelta(minutes=15)
                )
                
                # If conflict found, shift by 30 minutes
                while conflicts:
                    self.logger.warning(f"Conflict detected, adjusting time...")
                    scheduled_time = scheduled_time + timedelta(minutes=30)
                    
                    conflicts = await db_manager.get_scheduled_calls_for_lead(
                        lead_id,
                        start_time=scheduled_time - timedelta(minutes=15),
                        end_time=scheduled_time + timedelta(minutes=15)
                    )
                
                return scheduled_time
                
        except Exception as e:
            self.logger.warning(f"Conflict check failed: {e}, proceeding anyway")
            return scheduled_time
    
    async def _save_to_db(
        self,
        lead_id: str,
        scheduled_time: datetime,
        call_type: str,
        channel: str = "call",
        priority: str = "medium"
    ):
        """Save scheduled call to database"""
        
        async with get_db() as db:
            db_manager = DBManager(db)
            
            await db_manager.create_followup(
                lead_id=lead_id,
                scheduled_time=scheduled_time,
                followup_type=call_type,
                channel=channel,
                message_template=None
            )
            
            self.logger.info(f"✓ Saved: {call_type} at {scheduled_time}")
    
    async def _execute_urgent_callback(
        self,
        lead_id: str,
        scheduled_time: datetime
    ):
        """Execute urgent callback via background task"""
        
        # Wait until scheduled time
        delay_seconds = (scheduled_time - datetime.utcnow()).total_seconds()
        
        if delay_seconds > 0:
            self.logger.info(f"Waiting {delay_seconds:.0f}s for urgent callback")
            await asyncio.sleep(delay_seconds)
        
        self.logger.info(f"⚡ Triggering urgent callback for lead {lead_id}")
        
        # ExecuteCallWorker will pick up from DB
        # This just ensures it's triggered on time


# Export singleton
scheduler_agent = SchedulerAgent()