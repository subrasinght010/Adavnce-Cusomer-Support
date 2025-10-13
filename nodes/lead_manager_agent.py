# langchain_agents/lead_manager_agent.py
"""
Lead Manager Agent - Outbound Orchestrator
Handles: fetching leads, validation, scoring, scheduling, follow-ups, DB saves
Runs continuously in background (every 15 min)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import re

from database.crud import DBManager
from database.db import get_db
from state.workflow_state import (
    OptimizedWorkflowState, 
    calculate_lead_score,
    CallType,
    ClientType,
    LeadStage
)

logger = logging.getLogger(__name__)


class LeadManagerAgent:
    """
    Continuous orchestrator for outbound operations
    Merges: lead fetching, validation, scoring, scheduling, DB saves
    """
    
    def __init__(self):
        self.name = "lead_manager"
        self.is_running = False
        self.check_interval = 900  # 15 minutes
        
        # Approval queue (pending human approval)
        self.approval_queue: List[Dict[str, Any]] = []
        
        logger.info("✓ Lead Manager Agent initialized")
    
    async def start_continuous_operation(self):
        """Start continuous background loop"""
        self.is_running = True
        logger.info("🚀 Lead Manager started - continuous operation every 15 min")
        
        while self.is_running:
            try:
                await self._process_leads_cycle()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Lead Manager cycle failed: {e}")
                await asyncio.sleep(60)
    
    async def stop(self):
        """Stop continuous operation"""
        self.is_running = False
        logger.info("🛑 Lead Manager stopped")
    
    async def _process_leads_cycle(self):
        """Main processing cycle"""
        
        logger.info("=" * 60)
        logger.info("🔄 Lead Manager Cycle Starting")
        logger.info("=" * 60)
        
        # Step 1: Fetch new leads
        raw_leads = await self._fetch_leads_from_db()
        logger.info(f"Fetched {len(raw_leads)} leads from database")
        
        if not raw_leads:
            logger.info("No new leads to process")
            return
        
        # Step 2: Clean and validate
        validated_leads = await self._validate_leads(raw_leads)
        logger.info(f"Validated {len(validated_leads)}/{len(raw_leads)} leads")
        
        # Step 3: Score and classify
        scored_leads = await self._score_and_classify(validated_leads)
        
        # Step 4: Assign call types and client types
        enriched_leads = await self._enrich_leads(scored_leads)
        
        # Step 5: Build approval queue
        await self._build_approval_queue(enriched_leads)
        
        # Step 6: Schedule approved leads
        await self._schedule_approved_leads()
        
        # Step 7: Handle follow-ups
        await self._process_follow_ups()
        
        logger.info("✓ Lead Manager cycle complete")
    
    async def _fetch_leads_from_db(self) -> List[Dict]:
        """Fetch uncontacted or due-for-follow-up leads"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Get leads that need contact
                new_leads = await db_manager.get_leads_by_status("new", limit=50)
                followup_leads = await db_manager.get_leads_due_for_followup(limit=50)
                
                # Convert to dicts
                all_leads = []
                for lead in (new_leads + followup_leads):
                    all_leads.append({
                        "lead_id": lead.id,
                        "name": lead.name,
                        "email": lead.email,
                        "phone": lead.phone,
                        "company": lead.company,
                        "title": lead.title,
                        "status": lead.status,
                        "lead_score": lead.lead_score or 50,
                        "attempt_count": lead.attempt_count or 0,
                        "last_contact_date": lead.last_contact_date
                    })
                
                return all_leads
        
        except Exception as e:
            logger.error(f"Failed to fetch leads: {e}")
            return []
    
    async def _validate_leads(self, leads: List[Dict]) -> List[Dict]:
        """Validate email and phone format"""
        
        validated = []
        
        for lead in leads:
            issues = []
            
            # Validate email
            if lead.get("email"):
                if not self._validate_email(lead["email"]):
                    issues.append("invalid_email")
            else:
                issues.append("missing_email")
            
            # Validate phone
            if lead.get("phone"):
                if not self._validate_phone(lead["phone"]):
                    issues.append("invalid_phone")
            else:
                issues.append("missing_phone")
            
            # Must have at least one valid contact method
            if "invalid_email" in issues and "invalid_phone" in issues:
                logger.warning(f"Lead {lead['lead_id']} has no valid contact method - skipping")
                continue
            
            lead["validation_issues"] = issues
            validated.append(lead)
        
        return validated
    
    def _validate_email(self, email: str) -> bool:
        """Email format validation"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_phone(self, phone: str) -> bool:
        """Phone format validation"""
        digits = re.sub(r'\D', '', phone)
        return 10 <= len(digits) <= 15
    
    async def _score_and_classify(self, leads: List[Dict]) -> List[Dict]:
        """Score leads and determine stage"""
        
        for lead in leads:
            # Calculate score using existing function
            state = OptimizedWorkflowState(
                lead_data=lead,
                conversation_history=[],
                intelligence_output={}
            )
            score = calculate_lead_score(state)
            lead["lead_score"] = score
            
            # Classify by score
            if score >= 70:
                lead["lead_stage"] = LeadStage.QUALIFIED
                lead["priority"] = "high"
            elif score >= 40:
                lead["lead_stage"] = LeadStage.CONTACTED
                lead["priority"] = "medium"
            else:
                lead["lead_stage"] = LeadStage.NURTURE
                lead["priority"] = "low"
        
        return leads
    
    async def _enrich_leads(self, leads: List[Dict]) -> List[Dict]:
        """Assign call_type and client_type"""
        
        for lead in leads:
            # Determine call type based on history
            attempt_count = lead.get("attempt_count", 0)
            score = lead.get("lead_score", 50)
            last_contact = lead.get("last_contact_date")
            
            if attempt_count == 0:
                lead["call_type"] = CallType.COLD
            elif score >= 70:
                lead["call_type"] = CallType.HOT
            elif last_contact and self._days_since(last_contact) > 30:
                lead["call_type"] = CallType.FOLLOW_UP
            else:
                lead["call_type"] = CallType.WARM
            
            # Determine client type based on title/company
            title = (lead.get("title") or "").lower()
            company = (lead.get("company") or "").lower()
            
            if any(word in title for word in ["ceo", "cto", "founder", "director"]):
                lead["client_type"] = ClientType.PROFESSIONAL
            elif "enterprise" in company or "inc" in company:
                lead["client_type"] = ClientType.ENTERPRISE
            elif attempt_count > 0:
                lead["client_type"] = ClientType.RETURNING
            else:
                lead["client_type"] = ClientType.FIRST_TIME
        
        return leads
    
    def _days_since(self, date_str: str) -> int:
        """Calculate days since date"""
        try:
            last_date = datetime.fromisoformat(date_str)
            return (datetime.utcnow() - last_date).days
        except:
            return 999
    
    async def _build_approval_queue(self, leads: List[Dict]):
        """Add leads to approval queue"""
        
        # Filter out low priority for now
        high_priority = [l for l in leads if l.get("priority") != "low"]
        
        self.approval_queue.extend(high_priority)
        
        logger.info(f"Added {len(high_priority)} leads to approval queue")
        logger.info(f"Total pending approval: {len(self.approval_queue)}")
    
    async def get_approval_queue(self) -> List[Dict]:
        """Get current approval queue (for dashboard)"""
        return self.approval_queue
    
    async def approve_leads(self, lead_ids: List[str], approved_by: str) -> int:
        """Approve leads for contact"""
        
        approved_count = 0
        
        for lead_id in lead_ids:
            # Find lead in queue
            lead = next((l for l in self.approval_queue if l["lead_id"] == lead_id), None)
            
            if not lead:
                continue
            
            # Mark as approved
            lead["approved_for_contact"] = True
            lead["approval_timestamp"] = datetime.utcnow().isoformat()
            lead["approved_by"] = approved_by
            
            # Schedule it
            await self._schedule_lead(lead)
            
            # Remove from approval queue
            self.approval_queue.remove(lead)
            
            approved_count += 1
        
        logger.info(f"✓ Approved {approved_count} leads for contact")
        return approved_count
    
    async def _schedule_approved_leads(self):
        """Schedule leads that are already approved (auto-approval mode)"""
        
        # For now, no auto-approval - all go to human approval
        # Future: add auto-approval for high-confidence leads
        pass
    
    async def _schedule_lead(self, lead: Dict):
        """Schedule outbound contact for lead"""
        
        try:
            # Calculate best time
            scheduled_time = self._calculate_best_time(lead)
            
            # Determine channel priority
            channels = self._determine_channel_sequence(lead)
            
            # Save to database
            async with get_db() as db:
                db_manager = DBManager(db)
                
                schedule_record = {
                    "lead_id": lead["lead_id"],
                    "call_type": lead["call_type"].value,
                    "client_type": lead["client_type"].value,
                    "scheduled_time": scheduled_time.isoformat(),
                    "channels": channels,
                    "status": "pending",
                    "attempt_number": lead.get("attempt_count", 0) + 1
                }
                
                await db_manager.create_scheduled_call(schedule_record)
            
            logger.info(f"✓ Scheduled {lead['call_type'].value} call for lead {lead['lead_id']} at {scheduled_time}")
        
        except Exception as e:
            logger.error(f"Failed to schedule lead {lead.get('lead_id')}: {e}")
    
    def _calculate_best_time(self, lead: Dict) -> datetime:
        """Calculate optimal contact time"""
        
        now = datetime.utcnow()
        
        # Business hours: 9 AM - 6 PM
        # TODO: Add timezone handling
        
        # If current time is business hours, schedule 2 hours from now
        # Otherwise, schedule for tomorrow at 10 AM
        
        hour = now.hour
        
        if 9 <= hour < 16:  # Before 4 PM
            return now + timedelta(hours=2)
        else:
            # Tomorrow at 10 AM
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    
    def _determine_channel_sequence(self, lead: Dict) -> List[str]:
        """Determine multi-touch sequence"""
        
        call_type = lead.get("call_type")
        validation_issues = lead.get("validation_issues", [])
        
        # Build sequence based on call type and available channels
        sequence = []
        
        if call_type == CallType.COLD:
            # Cold: SMS → WhatsApp → Call → Email
            if "invalid_phone" not in validation_issues:
                sequence.extend(["sms", "whatsapp", "call"])
            if "invalid_email" not in validation_issues:
                sequence.append("email")
        
        elif call_type == CallType.HOT:
            # Hot: Direct call
            if "invalid_phone" not in validation_issues:
                sequence.append("call")
            else:
                sequence.append("email")
        
        else:
            # Warm/Follow-up: WhatsApp → Call → Email
            if "invalid_phone" not in validation_issues:
                sequence.extend(["whatsapp", "call"])
            if "invalid_email" not in validation_issues:
                sequence.append("email")
        
        return sequence
    
    async def _process_follow_ups(self):
        """Handle follow-up scheduling for existing leads"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Get leads that need follow-up
                due_followups = await db_manager.get_due_followups()
                
                for followup in due_followups:
                    # Create new outbound task
                    lead = await db_manager.get_lead(followup.lead_id)
                    
                    if lead:
                        lead_dict = {
                            "lead_id": lead.id,
                            "name": lead.name,
                            "email": lead.email,
                            "phone": lead.phone,
                            "company": lead.company,
                            "call_type": CallType.FOLLOW_UP,
                            "client_type": ClientType.RETURNING,
                            "approved_for_contact": True,  # Follow-ups auto-approved
                            "attempt_count": lead.attempt_count
                        }
                        
                        await self._schedule_lead(lead_dict)
                        
                        # Mark followup as executed
                        await db_manager.update_followup_status(followup.id, "executed")
                
                logger.info(f"Processed {len(due_followups)} follow-ups")
        
        except Exception as e:
            logger.error(f"Follow-up processing failed: {e}")
    
    async def save_to_db(self, state: OptimizedWorkflowState):
        """Save state updates to database (called after conversations)"""
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                lead_update = {
                    "last_contact_date": datetime.utcnow().isoformat(),
                    "lead_score": state.get("lead_score"),
                    "status": state.get("lead_stage"),
                    "last_intent": state.get("detected_intent"),
                    "last_sentiment": state.get("sentiment"),
                    "attempt_count": state.get("attempt_count", 0) + 1
                }
                
                await db_manager.update_lead(state.get("lead_id"), lead_update)
                
                # Save conversation
                conversation_record = {
                    "lead_id": state.get("lead_id"),
                    "session_id": state.get("session_id"),
                    "direction": state.get("direction"),
                    "channel": state.get("channel"),
                    "message": state.get("current_message"),
                    "response": state.get("intelligence_output", {}).get("response_text"),
                    "intent": state.get("detected_intent"),
                    "sentiment": state.get("sentiment"),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await db_manager.save_conversation(conversation_record)
                
                logger.info(f"✓ DB updated for lead {state.get('lead_id')}")
        
        except Exception as e:
            logger.error(f"DB save failed: {e}")


# Export singleton
lead_manager_agent = LeadManagerAgent()