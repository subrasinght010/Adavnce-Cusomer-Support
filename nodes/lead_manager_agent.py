# nodes/lead_manager_agent.py
"""
Lead Manager Agent - DB operations and follow-up management
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from database.db import get_db
from database.crud import DBManager
from state.workflow_state import DirectionType, OptimizedWorkflowState

logger = logging.getLogger(__name__)


class LeadManagerAgent:
    """Manages lead lifecycle, follow-ups, and conversions"""
    
    def __init__(self):
        self.logger = logger
    
    # ============================================================================
    # SAVE TO DB (Called after workflow)
    # ============================================================================
    
    async def save_to_db(self, state: OptimizedWorkflowState):
        """Save workflow state to database"""
        if not state.get("lead_id"):
            self.logger.error("Cannot save: missing lead_id")
            return
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                lead_id = int(state.get("lead_id"))
                
                # Update lead
                lead_update = {
                    "last_contacted_at": datetime.now(),
                    "engagement_score": state.get("engagement_score", 0)
                }
                
                if state.get("lead_status"):
                    lead_update["lead_status"] = state["lead_status"]
                
                await db_manager.update_lead(lead_id, lead_update)
                
                # Determine direction and save accordingly
                direction = state.get("direction")
                ts = datetime.now()
                if direction == DirectionType.INBOUND:
                    # INBOUND: Save user message first, then AI response
                    if state.get("current_message"):
                        await db_manager.add_conversation(
                            lead_id=lead_id,
                            message=state["current_message"],
                            channel=str(state.get("channel", "unknown")),
                            sender="user",
                            message_id=state.get("message_id"),
                            intent_detected=state.get("detected_intent"),
                            timestamp=ts  # explicitly pass timestamp
                        )
                    
                    # Then save AI response
                    intelligence = state.get("intelligence_output", {})
                    if intelligence.get("response_text"):
                        await db_manager.add_conversation(
                            lead_id=lead_id,
                            message=intelligence["response_text"],
                            channel=str(state.get("channel", "unknown")),
                            sender="ai",
                            intent_detected=state.get("detected_intent"),
                            cost=state.get("total_cost", 0.0),
                            campaign_id=state.get("campaign_id"),
                            timestamp=ts + timedelta(seconds=1) # explicitly pass timestamp
                        )
                
                else:  # OUTBOUND
                    # OUTBOUND: Only save AI message
                    intelligence = state.get("intelligence_output", {})
                    if intelligence.get("response_text"):
                        await db_manager.add_conversation(
                            lead_id=lead_id,
                            message=intelligence["response_text"],
                            channel=str(state.get("channel", "unknown")),
                            sender="ai",
                            intent_detected=state.get("detected_intent"),
                            cost=state.get("total_cost", 0.0),
                            campaign_id=state.get("campaign_id")
                        )
                
                self.logger.info(f"✓ State saved for lead {lead_id}")
        
        except Exception as e:
            self.logger.error(f"Save failed: {e}", exc_info=True)

        

    # ============================================================================
    # FOLLOW-UP MANAGEMENT
    # ============================================================================



    async def process_due_followups(self):
        """Process pending follow-ups (call from background worker)"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Get due follow-ups
                followups = await db_manager.get_pending_followups(limit=50)
                
                if not followups:
                    return
                
                self.logger.info(f"Processing {len(followups)} follow-ups")
                
                for followup in followups:
                    try:
                        await self._execute_followup(followup, db_manager)
                    except Exception as e:
                        self.logger.error(f"Follow-up {followup.id} failed: {e}")
                        await db_manager.update_followup_status(followup.id, "failed")
        
        except Exception as e:
            self.logger.error(f"Follow-up processing failed: {e}")
    
    async def _execute_followup(self, followup, db_manager: DBManager):
        """Execute single follow-up"""
        
        # Get lead
        lead = await db_manager.get_lead_by_id(followup.lead_id)
        if not lead:
            return
        
        # Import here to avoid circular dependency
        from state.workflow_state import create_initial_state
        from graph_workflows.workflow import workflow_router
        
        # Create outbound state
        state = create_initial_state(
            lead_id=str(lead.id),
            message=followup.message_template or "",
            channel=followup.channel,
            direction="outbound",
            call_type="follow_up",
            lead_data={
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone
            }
        )
        
        # Run workflow
        result = await workflow_router.run(state)
        
        # Update status
        if result.get("communication_sent"):
            await db_manager.update_followup_status(followup.id, "sent")
            self.logger.info(f"✓ Follow-up sent: {followup.id}")
            
            # Schedule next follow-up if needed
            await self._schedule_next_followup(lead, followup, db_manager)
        else:
            await db_manager.update_followup_status(followup.id, "failed")
    
    async def _schedule_next_followup(self, lead, current_followup, db_manager: DBManager):
        """Schedule next follow-up in sequence"""
        
        # Channel progression
        channel_map = {
            "email": "sms",
            "sms": "whatsapp",
            "whatsapp": "call"
        }
        
        # Delay progression
        delay_map = {
            "email": timedelta(hours=24),
            "sms": timedelta(hours=48),
            "whatsapp": timedelta(hours=72),
            "call": timedelta(hours=96)
        }
        
        next_channel = channel_map.get(current_followup.channel)
        if not next_channel:
            return  # End of sequence
        
        delay = delay_map.get(current_followup.channel, timedelta(hours=24))
        next_time = datetime.now() + delay
        
        await db_manager.create_followup(
            lead_id=lead.id,
            scheduled_time=next_time,
            followup_type="reminder",
            channel=next_channel
        )
        
        self.logger.info(f"Next follow-up scheduled: {next_channel} at {next_time}")
    
    # ============================================================================
    # LEAD CONVERSION
    # ============================================================================
    
    async def convert_lead_to_client(
        self,
        lead_id: int,
        user_id: int,
        plan_type: str = None,
        mrr: float = 0.0
    ):
        """Convert lead to client"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                client = await db_manager.convert_lead_to_client(
                    lead_id=lead_id,
                    user_id=user_id,
                    plan_type=plan_type,
                    mrr=mrr
                )
                
                self.logger.info(f"✓ Lead {lead_id} converted to client {client.id}")
                return client
        
        except Exception as e:
            self.logger.error(f"Conversion failed: {e}")
            raise
    
    # ============================================================================
    # MANUAL OPERATIONS
    # ============================================================================
    
    async def create_manual_followup(
        self,
        lead_id: int,
        hours_delay: int = 24,
        followup_type: str = "reminder",
        channel: str = "email"
    ):
        """Manually schedule follow-up"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                scheduled_time = datetime.now() + timedelta(hours=hours_delay)
                
                followup = await db_manager.create_followup(
                    lead_id=lead_id,
                    scheduled_time=scheduled_time,
                    followup_type=followup_type,
                    channel=channel
                )
                
                self.logger.info(f"Manual follow-up created: {followup.id}")
                return followup
        
        except Exception as e:
            self.logger.error(f"Manual follow-up failed: {e}")
            raise


# Export singleton
lead_manager_agent = LeadManagerAgent()