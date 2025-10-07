# workers/execute_call_worker.py
"""
Execute Scheduled Calls Worker - COMPLETE WORKFLOW INTEGRATION

When executing a scheduled call:
1. Initiates the call
2. Call conversation goes through FULL WORKFLOW:
   - Intent Detection
   - Knowledge Agent (RAG)
   - Communication (might send email/SMS after call)
   - Scheduling (might schedule another callback)
   - Verification
   - DB Update
   - Follow-ups
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

# Database
from database.crud import DBManager
from database.db import get_db
from database.models import Followup, Lead

# Services
from services.phone_service import PhoneService

# CRITICAL: Import the FULL workflow
from graph_workflows.optimized_workflow import workflow_runner

logger = logging.getLogger(__name__)


class ExecuteCallWorker:
    """
    Background worker that executes scheduled calls
    
    Important: Each call conversation runs through the COMPLETE workflow,
    which means during/after the call, the system can:
    - Detect new intents
    - Send follow-up emails/SMS
    - Schedule another callback
    - Update database
    - Verify data
    """
    
    def __init__(self):
        self.phone_service = PhoneService()
        self.is_running = False
        self.check_interval = 60  # Check every 60 seconds
        
        # Store active calls to handle conversation flow
        self.active_calls = {}  # {call_sid: {lead_id, followup_id, conversation}}
        
    async def start(self):
        """Start the worker"""
        self.is_running = True
        logger.info("🚀 Execute Call Worker started - checking every 60s")
        
        while self.is_running:
            try:
                await self._process_scheduled_calls()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in execute call worker: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Stop the worker"""
        self.is_running = False
        logger.info("🛑 Execute Call Worker stopped")
    
    async def _process_scheduled_calls(self):
        """
        Main processing loop:
        1. Get scheduled calls from database
        2. Filter calls that are due now
        3. Execute each call through FULL workflow
        """
        
        try:
            async with get_db() as db:
                db_manager = DBManager(db)
                
                # Get pending callbacks
                pending_callbacks = await db_manager.get_pending_followups()
                
                if not pending_callbacks:
                    return
                
                # Filter callbacks that are due now
                now = datetime.utcnow()
                due_callbacks = [
                    cb for cb in pending_callbacks
                    if cb.scheduled_time <= now and cb.followup_type == "callback"
                ]
                
                if not due_callbacks:
                    return
                
                logger.info(f"⏰ Executing {len(due_callbacks)} scheduled callbacks")
                
                # Execute each callback
                for callback in due_callbacks:
                    await self._execute_single_call(callback, db_manager)
        
        except Exception as e:
            logger.error(f"Failed to process scheduled calls: {e}")
    
    async def _execute_single_call(self, callback: Followup, db_manager: DBManager):
        """
        Execute a single scheduled call and run through COMPLETE workflow
        
        Flow:
        1. Get lead data from database
        2. Initiate call via phone service
        3. Mark callback as in_progress
        4. Send initial greeting through FULL WORKFLOW
        5. Handle call conversation (each message goes through workflow)
        6. After call ends, mark as completed
        """
        
        try:
            logger.info(f"📞 Executing callback for lead: {callback.lead_id}")
            
            # 1. Get lead data
            lead = await db_manager.get_lead(callback.lead_id)
            if not lead:
                logger.error(f"Lead not found: {callback.lead_id}")
                return
            
            # 2. Verify lead has phone number
            if not lead.phone:
                logger.error(f"Lead {callback.lead_id} has no phone number")
                await db_manager.update_followup(
                    callback.id, 
                    status="failed",
                    notes="No phone number"
                )
                return
            
            # 3. Initiate call
            logger.info(f"📱 Calling {lead.phone}...")
            
            call_result = await self.phone_service.initiate_call(
                to_number=lead.phone,
                lead_id=lead.id,
                callback_url=f"/webhook/call/{callback.id}"
            )
            
            if not call_result.get("success"):
                logger.error(f"Call failed: {call_result.get('error')}")
                await db_manager.update_followup(
                    callback.id,
                    status="failed",
                    notes=call_result.get("error")
                )
                return
            
            call_sid = call_result.get("call_sid")
            
            # 4. Mark callback as in_progress
            await db_manager.update_followup(
                callback.id,
                status="in_progress",
                notes=f"Call initiated: {call_sid}"
            )
            
            # 5. Store active call info
            self.active_calls[call_sid] = {
                "lead_id": lead.id,
                "followup_id": callback.id,
                "conversation": [],
                "started_at": datetime.utcnow()
            }
            
            # 6. Send initial greeting through FULL WORKFLOW
            initial_message = (
                f"Hello {lead.name}, this is your scheduled callback. "
                f"How can I help you today?"
            )
            
            # CRITICAL: Run through COMPLETE workflow
            # This goes through:
            # - Incoming Listener
            # - Intent Detection
            # - Knowledge Agent (RAG)
            # - Communication (might send follow-up)
            # - Scheduling (might schedule another call)
            # - Verification
            # - DB Update
            # - Follow-ups
            
            result = await workflow_runner.run(
                lead_id=lead.id,
                message=initial_message,
                channel="call",
                lead_data={
                    "name": lead.name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "context": "scheduled_callback",
                    "call_sid": call_sid,
                    "followup_id": callback.id
                }
            )
            
            logger.info(f"✅ Initial greeting sent for callback {callback.id}")
            logger.info(f"   Response: {result.get('final_response', '')[:100]}...")
            
            # The rest of the conversation will come through /webhook/call/{callback.id}
            # Each message will also go through the COMPLETE workflow
            
        except Exception as e:
            logger.error(f"Failed to execute callback {callback.id}: {e}")
            
            try:
                await db_manager.update_followup(
                    callback.id,
                    status="failed",
                    notes=str(e)
                )
            except:
                pass
    
    async def handle_call_message(
        self, 
        call_sid: str, 
        user_message: str,
        db_manager: DBManager
    ) -> Dict:
        """
        Handle message during active call
        
        IMPORTANT: Each message goes through FULL WORKFLOW
        This means during the call, the workflow can:
        - Detect intent (e.g., "send me pricing via email")
        - Trigger email/SMS (Communication Agent)
        - Schedule another callback (Scheduling Agent)
        - Update database
        """
        
        if call_sid not in self.active_calls:
            logger.warning(f"Unknown call SID: {call_sid}")
            return {"error": "Call not found"}
        
        call_info = self.active_calls[call_sid]
        lead_id = call_info["lead_id"]
        
        # Get lead data
        lead = await db_manager.get_lead(lead_id)
        
        # Add to conversation history
        call_info["conversation"].append({
            "role": "user",
            "message": user_message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"📞 Call message from {lead_id}: {user_message}")
        
        # CRITICAL: Run through COMPLETE workflow
        # Example: User says "Can you email me the pricing?"
        # Workflow will:
        # 1. Detect intent: "request_pricing" + "send_email"
        # 2. Generate pricing response
        # 3. Communication Agent sends email with pricing
        # 4. Respond on call: "I've just sent you an email with our pricing"
        
        result = await workflow_runner.run(
            lead_id=lead_id,
            message=user_message,
            channel="call",
            lead_data={
                "name": lead.name,
                "phone": lead.phone,
                "email": lead.email,
                "context": "ongoing_call",
                "call_sid": call_sid,
                "conversation_history": call_info["conversation"]
            }
        )
        
        # Extract AI response
        ai_response = result.get("final_response", "I understand. How else can I help?")
        
        # Add AI response to conversation
        call_info["conversation"].append({
            "role": "assistant",
            "message": ai_response,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Check if workflow scheduled a callback or sent communication
        actions_taken = []
        
        if result.get("communication_sent"):
            actions_taken.append(
                f"Sent {result.get('communication_channel_used', 'message')}"
            )
        
        if result.get("callback_scheduled"):
            actions_taken.append(
                f"Scheduled callback for {result.get('callback_time', 'later')}"
            )
        
        if actions_taken:
            logger.info(f"   Actions during call: {', '.join(actions_taken)}")
        
        return {
            "response": ai_response,
            "actions": actions_taken,
            "intent": result.get("detected_intent"),
            "sentiment": result.get("sentiment")
        }
    
    async def end_call(self, call_sid: str, db_manager: DBManager):
        """
        Mark call as completed
        """
        
        if call_sid not in self.active_calls:
            return
        
        call_info = self.active_calls[call_sid]
        followup_id = call_info["followup_id"]
        
        # Calculate call duration
        duration = (datetime.utcnow() - call_info["started_at"]).total_seconds()
        
        # Update followup status
        await db_manager.update_followup(
            followup_id,
            status="completed",
            notes=f"Call completed. Duration: {duration}s. Messages: {len(call_info['conversation'])}"
        )
        
        logger.info(f"✅ Call {call_sid} completed ({duration}s)")
        
        # Remove from active calls
        del self.active_calls[call_sid]


# Global instance
execute_call_worker = ExecuteCallWorker()