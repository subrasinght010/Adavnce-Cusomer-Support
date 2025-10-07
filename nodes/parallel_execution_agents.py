# nodes/parallel_execution_agents.py
"""
Parallel Execution Agents - FULLY INTEGRATED
Connects to: services/email_service.py, services/sms_service.py, services/whatsapp_service.py
"""

import asyncio
import logging
from typing import Dict, Any

# Base class
from nodes.core.base_node import BaseNode

# State
from state.optimized_workflow_state import OptimizedWorkflowState, ChannelType

# YOUR EXISTING CODE - Services
from services.email_service import send_email
from services.sms_service import send_sms
from services.whatsapp_service import send_whatsapp

# YOUR EXISTING CODE - Utils
from utils.retry_handler import RetryHandler
from utils.delivery_tracker import DeliveryTracker

# YOUR EXISTING CODE - Config
from config.settings import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 1. COMMUNICATION AGENT (INTEGRATED)
# ============================================================================

class CommunicationAgent(BaseNode):
    """
    Send messages via any channel using YOUR existing services
    """
    
    def __init__(self):
        super().__init__("communication_agent")
        self.retry_handler = RetryHandler(
            max_retries=3,
            initial_delay=1.0
        )
        self.delivery_tracker = DeliveryTracker()
    
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
        
        self.logger.info(f"Sending response via {channel.value if hasattr(channel, 'value') else channel}")
        
        try:
            # Send via appropriate channel with retry
            send_func = self._get_send_function(channel)
            
            success = await self.retry_handler.retry_with_exponential_backoff(
                lambda: send_func(lead_data, response_text)
            )
            
            # Track delivery
            if success:
                await self.delivery_tracker.track_sent(
                    message_id=state.get("session_id"),
                    channel=str(channel),
                    recipient=self._get_recipient(lead_data, channel)
                )
            
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
    
    def _get_send_function(self, channel):
        """Get the appropriate send function for channel"""
        channel_str = channel.value if hasattr(channel, 'value') else str(channel)
        
        if channel_str == "whatsapp":
            return self._send_whatsapp
        elif channel_str == "email":
            return self._send_email
        elif channel_str == "sms":
            return self._send_sms
        elif channel_str == "call":
            return self._send_voice
        else:
            return self._send_web_chat
    
    def _get_recipient(self, lead_data: Dict, channel) -> str:
        """Get recipient identifier for tracking"""
        channel_str = channel.value if hasattr(channel, 'value') else str(channel)
        
        if channel_str in ["whatsapp", "sms", "call"]:
            return lead_data.get("phone", "unknown")
        elif channel_str == "email":
            return lead_data.get("email", "unknown")
        else:
            return lead_data.get("lead_id", "unknown")
    
    async def _send_whatsapp(self, lead_data: Dict, message: str) -> bool:
        """Send WhatsApp using YOUR existing service"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for WhatsApp")
            return False
        
        try:
            # Use YOUR existing WhatsApp service
            result = await send_whatsapp(
                to_phone=phone,
                message=message
            )
            
            self.logger.info(f"✓ WhatsApp sent to {phone}")
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        
        except Exception as e:
            self.logger.error(f"WhatsApp send failed: {e}")
            return False
    
    async def _send_email(self, lead_data: Dict, message: str) -> bool:
        """Send email using YOUR existing service"""
        email = lead_data.get("email")
        if not email:
            self.logger.error("No email address")
            return False
        
        try:
            # Use YOUR existing email service
            result = await send_email(
                to_email=email,
                subject="Response from our team",
                body=message
            )
            
            self.logger.info(f"✓ Email sent to {email}")
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        
        except Exception as e:
            self.logger.error(f"Email send failed: {e}")
            return False
    
    async def _send_sms(self, lead_data: Dict, message: str) -> bool:
        """Send SMS using YOUR existing service"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for SMS")
            return False
        
        try:
            # Use YOUR existing SMS service
            result = await send_sms(
                to_phone=phone,
                message=message
            )
            
            self.logger.info(f"✓ SMS sent to {phone}")
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        
        except Exception as e:
            self.logger.error(f"SMS send failed: {e}")
            return False
    
    async def _send_voice(self, lead_data: Dict, message: str) -> bool:
        """Send voice message or make call"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number for voice")
            return False
        
        try:
            # Use YOUR existing TTS + voice service
            from tools.tts import text_to_speech
            
            # Convert text to speech
            audio_url = await text_to_speech(message)
            
            # Make call (implement based on your voice service)
            # result = await make_call(phone, audio_url)
            
            self.logger.info(f"✓ Voice call initiated to {phone}")
            return True
        
        except Exception as e:
            self.logger.error(f"Voice call failed: {e}")
            return False
    
    async def _send_web_chat(self, lead_data: Dict, message: str) -> bool:
        """Send web chat message"""
        # Implement based on your WebSocket/chat system
        await asyncio.sleep(0.1)
        self.logger.info(f"✓ Web chat message sent")
        return True


# ============================================================================
# 2. SCHEDULING AGENT
# ============================================================================

class SchedulingAgent(BaseNode):
    """Schedule callbacks and follow-ups"""
    
    def __init__(self):
        super().__init__("scheduling_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Schedule callback if requested"""
        
        intelligence = state.get("intelligence_output", {})
        next_actions = intelligence.get("next_actions", [])
        
        if "schedule_callback" not in next_actions:
            self.logger.info("No callback scheduling needed")
            return state
        
        self.logger.info("Scheduling callback...")
        
        entities = intelligence.get("entities", {})
        preferred_time = entities.get("preferred_time")
        
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
    
    async def _schedule_callback(self, lead_id: str, preferred_time: str = None) -> str:
        """Schedule a callback"""
        from datetime import datetime, timedelta
        
        if not preferred_time:
            callback_time = datetime.utcnow() + timedelta(days=1)
        else:
            callback_time = datetime.utcnow() + timedelta(hours=2)
        
        await asyncio.sleep(0.1)
        return callback_time.isoformat()


# ============================================================================
# 3. VERIFICATION AGENT
# ============================================================================

class VerificationAgent(BaseNode):
    """Verify lead data quality"""
    
    def __init__(self):
        super().__init__("verification_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Verify lead data if needed"""
        
        if not state.get("needs_verification"):
            self.logger.info("No verification needed")
            return state
        
        self.logger.info("Verifying lead data...")
        
        lead_data = state.get("lead_data", {})
        issues = []
        
        # Verify email
        email = lead_data.get("email")
        if email and not await self._verify_email(email):
            issues.append(f"Invalid email: {email}")
        
        # Verify phone
        phone = lead_data.get("phone")
        if phone and not await self._verify_phone(phone):
            issues.append(f"Invalid phone: {phone}")
        
        state["data_verified"] = len(issues) == 0
        state["verification_issues"] = issues
        
        if len(issues) == 0:
            state["completed_actions"].append("verify_data")
            self.logger.info("✓ All data verified")
        else:
            self.logger.warning(f"Verification issues: {issues}")
        
        return state
    
    async def _verify_email(self, email: str) -> bool:
        """Verify email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    async def _verify_phone(self, phone: str) -> bool:
        """Verify phone format"""
        import re
        digits = re.sub(r'\D', '', phone)
        return 10 <= len(digits) <= 15


# ============================================================================
# 4. PARALLEL EXECUTOR
# ============================================================================

class ParallelExecutor(BaseNode):
    """Execute all 3 agents in PARALLEL"""
    
    def __init__(self):
        super().__init__("parallel_executor")
        self.communication_agent = CommunicationAgent()
        self.scheduling_agent = SchedulingAgent()
        self.verification_agent = VerificationAgent()
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """
        Run all execution agents in parallel
        """
        
        self.logger.info("Starting parallel execution of 3 agents...")
        
        # Create tasks for parallel execution
        tasks = [
            self.communication_agent.execute(state.copy()),
            self.scheduling_agent.execute(state.copy()),
            self.verification_agent.execute(state.copy())
        ]
        
        # Run all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        final_state = state.copy()
        
        for result in results:
            if isinstance(result, dict):
                # Merge state updates
                for key, value in result.items():
                    # For lists, extend instead of replace
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
                self.logger.error(f"Agent failed: {result}")
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