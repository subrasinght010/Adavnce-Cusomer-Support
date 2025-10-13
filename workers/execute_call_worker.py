# workers/execute_call_worker.py
"""
Execute Call Worker - Handles scheduled callback execution
"""

import asyncio
from datetime import datetime
from typing import Dict

from workers.base_worker import BaseWorker
from database.crud import DBManager
from database.models import FollowUp
from database.db import AsyncSessionLocal
from services.phone_service import PhoneService
from graph_workflows.workflow import workflow_runner


class ExecuteCallWorker(BaseWorker):
    """Execute scheduled callbacks through full workflow"""
    
    def __init__(self):
        super().__init__("execute_call")
        self.phone_service = PhoneService()
        self.check_interval = 60  # Check every 60 seconds
        self.active_calls = {}  # {call_sid: {lead_id, followup_id, conversation}}
    
    async def _run(self):
        """Main loop - check and execute scheduled calls"""
        while self.is_running:
            try:
                await self._process_scheduled_calls()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Error processing calls: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _process_scheduled_calls(self):
        """Get and execute due callbacks"""
        try:
            async with AsyncSessionLocal() as session:
                db_manager = DBManager(session)
                
                # Get pending callbacks
                pending_callbacks = await db_manager.get_pending_followups()
                
                if not pending_callbacks:
                    return
                
                # Filter due callbacks
                now = datetime.utcnow()
                due_callbacks = [
                    cb for cb in pending_callbacks
                    if cb.scheduled_time <= now and cb.followup_type == "callback"
                ]
                
                if not due_callbacks:
                    return
                
                self.logger.info(f"⏰ Executing {len(due_callbacks)} callbacks")
                
                # Execute each callback
                for callback in due_callbacks:
                    await self._execute_single_call(callback, db_manager)
        
        except Exception as e:
            self.logger.error(f"Failed to process scheduled calls: {e}")
    
    async def _execute_single_call(self, callback: FollowUp, db_manager: DBManager):
        """Execute single callback through full workflow"""
        try:
            self.logger.info(f"📞 Executing callback for lead: {callback.lead_id}")
            
            # Get lead data
            lead = await db_manager.get_lead(callback.lead_id)
            if not lead or not lead.phone:
                self.logger.error(f"Invalid lead data for {callback.lead_id}")
                await db_manager.update_followup(
                    callback.id, 
                    status="failed",
                    notes="No phone number"
                )
                return
            
            # Mark as in progress
            await db_manager.update_followup(callback.id, status="in_progress")
            
            # Initiate call
            call_sid = await self.phone_service.initiate_call(
                to_number=lead.phone,
                lead_id=lead.id
            )
            
            if not call_sid:
                await db_manager.update_followup(
                    callback.id,
                    status="failed",
                    notes="Call initiation failed"
                )
                return
            
            # Track active call
            self.active_calls[call_sid] = {
                'lead_id': lead.id,
                'followup_id': callback.id,
                'conversation': []
            }
            
            self.logger.info(f"✅ Call initiated: {call_sid}")
            
            # Mark as completed (call conversation handled by workflow)
            await db_manager.update_followup(
                callback.id,
                status="completed",
                notes=f"Call initiated: {call_sid}"
            )
        
        except Exception as e:
            self.logger.error(f"Failed to execute call: {e}")
            await db_manager.update_followup(
                callback.id,
                status="failed",
                notes=str(e)
            )
    
    def get_status(self) -> dict:
        """Enhanced status with call-specific info"""
        status = super().get_status()
        status.update({
            'check_interval': self.check_interval,
            'active_calls': len(self.active_calls),
            'phone_service': 'connected' if self.phone_service else 'disconnected'
        })
        return status


# Singleton instance
execute_call_worker = ExecuteCallWorker()