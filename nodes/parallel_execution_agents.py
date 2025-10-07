# nodes/parallel_execution_agents.py
"""
Execution agents that run in PARALLEL (not sequential)
- Communication Agent
- Scheduling Agent  
- Verification Agent

These don't use LLM - they just execute what Intelligence Agent decided
"""

import asyncio
from typing import Dict, Any
from nodes.core.base_node import BaseNode, with_timing
from state.optimized_workflow_state import OptimizedWorkflowState, ChannelType


# ============================================================================
# 1. COMMUNICATION AGENT
# ============================================================================

class CommunicationAgent(BaseNode):
    """
    Send messages via any channel (WhatsApp, Email, SMS, Call)
    No LLM calls - just uses response from Intelligence Agent
    """
    
    def __init__(self):
        super().__init__("communication_agent")
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Send communication via preferred channel
        """
        
        # Get response from intelligence agent
        intelligence = state.get("intelligence_output", {})
        response_text = intelligence.get("response_text", "")
        
        if not response_text:
            self.logger.warning("No response text to send")
            return state
        
        # Get channel and lead data
        channel = state.get("channel")
        lead_data = state.get("lead_data", {})
        
        self.logger.info(f"Sending response via {channel.value}")
        
        # Send via appropriate channel
        try:
            if channel == ChannelType.WHATSAPP:
                success = await self._send_whatsapp(lead_data, response_text)
            elif channel == ChannelType.EMAIL:
                success = await self._send_email(lead_data, response_text)
            elif channel == ChannelType.SMS:
                success = await self._send_sms(lead_data, response_text)
            elif channel == ChannelType.CALL:
                success = await self._send_voice(lead_data, response_text)
            else:
                success = await self._send_web_chat(lead_data, response_text)
            
            # Update state
            state["communication_sent"] = success
            state["communication_channel_used"] = channel
            state["communication_status"] = "sent" if success else "failed"
            
            if success:
                state["completed_actions"].append("send_response")
            
        except Exception as e:
            self.logger.error(f"Communication failed: {e}")
            state["communication_sent"] = False
            state["communication_status"] = f"error: {str(e)}"
        
        return state
    
    async def _send_whatsapp(self, lead_data: Dict, message: str) -> bool:
        """Send WhatsApp message"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for WhatsApp")
            return False
        
        # Simulate sending (replace with actual Twilio/WhatsApp API)
        await asyncio.sleep(0.2)
        self.logger.info(f"✓ WhatsApp sent to {phone}")
        return True
    
    async def _send_email(self, lead_data: Dict, message: str) -> bool:
        """Send email"""
        email = lead_data.get("email")
        if not email:
            self.logger.error("No email address")
            return False
        
        # Simulate sending (replace with actual SendGrid/SMTP)
        await asyncio.sleep(0.3)
        self.logger.info(f"✓ Email sent to {email}")
        return True
    
    async def _send_sms(self, lead_data: Dict, message: str) -> bool:
        """Send SMS"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for SMS")
            return False
        
        # Simulate sending (replace with actual Twilio SMS API)
        await asyncio.sleep(0.15)
        self.logger.info(f"✓ SMS sent to {phone}")
        return True
    
    async def _send_voice(self, lead_data: Dict, message: str) -> bool:
        """Send voice message or make call"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for voice")
            return False
        
        # Simulate call (replace with actual Twilio Voice API + TTS)
        await asyncio.sleep(0.25)
        self.logger.info(f"✓ Voice call initiated to {phone}")
        return True
    
    async def _send_web_chat(self, lead_data: Dict, message: str) -> bool:
        """Send web chat message"""
        # Simulate web chat (replace with WebSocket/polling)
        await asyncio.sleep(0.1)
        self.logger.info(f"✓ Web chat message sent")
        return True


# ============================================================================
# 2. SCHEDULING AGENT
# ============================================================================

class SchedulingAgent(BaseNode):
    """
    Schedule callbacks and follow-ups
    No LLM calls - just scheduling logic
    """
    
    def __init__(self):
        super().__init__("scheduling_agent")
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Schedule callback if requested
        """
        
        # Check if scheduling is needed
        intelligence = state.get("intelligence_output", {})
        next_actions = intelligence.get("next_actions", [])
        
        if "schedule_callback" not in next_actions:
            self.logger.info("No callback scheduling needed")
            return state
        
        self.logger.info("Scheduling callback...")
        
        # Extract callback time
        entities = intelligence.get("entities", {})
        preferred_time = entities.get("preferred_time")
        
        # Schedule callback
        try:
            callback_time = await self._schedule_callback(
                state.get("lead_id"),
                preferred_time
            )
            
            state["callback_scheduled"] = True
            state["callback_time"] = callback_time
            state["completed_actions"].append("schedule_callback")
            
            self.logger.info(f"✓ Callback scheduled for {callback_time}")
        
        except Exception as e:
            self.logger.error(f"Scheduling failed: {e}")
            state["callback_scheduled"] = False
        
        return state
    
    async def _schedule_callback(
        self, 
        lead_id: str, 
        preferred_time: str = None
    ) -> str:
        """
        Schedule a callback in the system
        Returns scheduled time
        """
        from datetime import datetime, timedelta
        
        # If no preferred time, schedule for tomorrow
        if not preferred_time:
            callback_time = datetime.utcnow() + timedelta(days=1)
        else:
            # Parse preferred time (simplified)
            # In real app, use proper date parsing
            callback_time = datetime.utcnow() + timedelta(hours=2)
        
        # Simulate scheduling (replace with actual task queue/scheduler)
        await asyncio.sleep(0.1)
        
        # In real app:
        # - Add to task queue (Celery, RQ, etc.)
        # - Store in database
        # - Set up reminder notification
        
        return callback_time.isoformat()


# ============================================================================
# 3. VERIFICATION AGENT
# ============================================================================

class VerificationAgent(BaseNode):
    """
    Verify lead data quality
    No LLM calls - just validation logic
    """
    
    def __init__(self):
        super().__init__("verification_agent")
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Verify lead data if needed
        """
        
        # Check if verification is needed
        if not state.get("needs_verification"):
            self.logger.info("No verification needed")
            return state
        
        self.logger.info("Verifying lead data...")
        
        lead_data = state.get("lead_data", {})
        issues = []
        
        # Verify email
        email = lead_data.get("email")
        if email:
            if not await self._verify_email(email):
                issues.append(f"Invalid email: {email}")
        
        # Verify phone
        phone = lead_data.get("phone")
        if phone:
            if not await self._verify_phone(phone):
                issues.append(f"Invalid phone: {phone}")
        
        # Update state
        state["data_verified"] = len(issues) == 0
        state["verification_issues"] = issues
        
        if len(issues) == 0:
            state["completed_actions"].append("verify_data")
            self.logger.info("✓ All data verified")
        else:
            self.logger.warning(f"Verification issues: {issues}")
        
        return state
    
    async def _verify_email(self, email: str) -> bool:
        """Verify email format and domain"""
        import re
        
        # Basic email regex
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(pattern, email):
            return False
        
        # Simulate domain check (in real app, check DNS/MX records)
        await asyncio.sleep(0.05)
        
        return True
    
    async def _verify_phone(self, phone: str) -> bool:
        """Verify phone format"""
        import re
        
        # Remove non-digits
        digits = re.sub(r'\D', '', phone)
        
        # Check length (10-15 digits is typical)
        if len(digits) < 10 or len(digits) > 15:
            return False
        
        # Simulate carrier lookup (in real app, use Twilio Lookup API)
        await asyncio.sleep(0.05)
        
        return True


# ============================================================================
# 4. PARALLEL EXECUTOR (Runs all 3 simultaneously)
# ============================================================================

class ParallelExecutor(BaseNode):
    """
    Execute Communication, Scheduling, and Verification in PARALLEL
    This is a key optimization - don't wait for each sequentially
    """
    
    def __init__(self):
        super().__init__("parallel_executor")
        self.communication_agent = CommunicationAgent()
        self.scheduling_agent = SchedulingAgent()
        self.verification_agent = VerificationAgent()
    
    @with_timing
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Run all execution agents in parallel
        """
        
        self.logger.info("Starting parallel execution of 3 agents...")
        
        # Create tasks for parallel execution
        tasks = [
            self.communication_agent.execute(state),
            self.scheduling_agent.execute(state),
            self.verification_agent.execute(state)
        ]
        
        # Run all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results (take last non-error state)
        final_state = state
        for result in results:
            if isinstance(result, dict):
                # Merge state updates
                final_state.update(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Agent failed: {result}")
                # Add error but continue
                if "errors" not in final_state:
                    final_state["errors"] = []
                final_state["errors"].append({
                    "node": "parallel_executor",
                    "error": str(result)
                })
        
        self.logger.info(
            f"✓ Parallel execution complete - "
            f"Communication: {final_state.get('communication_sent')}, "
            f"Callback: {final_state.get('callback_scheduled')}, "
            f"Verified: {final_state.get('data_verified')}"
        )
        
        return final_state


# ============================================================================
# Export instances
# ============================================================================

communication_agent = CommunicationAgent()
scheduling_agent = SchedulingAgent()
verification_agent = VerificationAgent()
parallel_executor = ParallelExecutor()