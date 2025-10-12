# nodes/parallel_execution_agents.py
"""
Parallel Execution Agents - UPDATED for Inbound/Outbound
"""

import asyncio
import logging
from typing import Dict, Any

from nodes.core.base_node import BaseNode
from state.optimized_workflow_state import OptimizedWorkflowState, ChannelType, DirectionType

# Services
from services.email_service import send_email
from services.sms_service import send_sms
from services.whatsapp_service import send_whatsapp

logger = logging.getLogger(__name__)


# ============================================================================
# 1. COMMUNICATION AGENT (UPDATED)
# ============================================================================

class CommunicationAgent(BaseNode):
    """Send messages via any channel"""
    
    def __init__(self):
        super().__init__("communication_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Send communication via channel"""
        
        intelligence = state.get("intelligence_output", {})
        response_text = intelligence.get("response_text", "")
        
        if not response_text:
            self.logger.warning("No response text to send")
            return state
        
        channel = state.get("channel")
        lead_data = state.get("lead_data", {})
        direction = state.get("direction")
        
        self.logger.info(f"[{direction}] Sending via {channel}")
        
        try:
            success = await self._send_message(channel, lead_data, response_text)
            
            if success:
                state["communication_sent"] = True
                state["communication_channel_used"] = channel
                state["completed_actions"].append("send_communication")
                self.logger.info("✓ Message sent")
            else:
                state["communication_sent"] = False
                self.logger.error("✗ Message failed")
        
        except Exception as e:
            self.logger.error(f"Communication failed: {e}")
            state["communication_sent"] = False
        
        return state
    
    async def _send_message(self, channel: ChannelType, lead_data: Dict, message: str) -> bool:
        """Route to correct service"""
        
        if channel == ChannelType.EMAIL or channel == "email":
            return await self._send_email(lead_data, message)
        elif channel == ChannelType.SMS or channel == "sms":
            return await self._send_sms(lead_data, message)
        elif channel == ChannelType.WHATSAPP or channel == "whatsapp":
            return await self._send_whatsapp(lead_data, message)
        elif channel == ChannelType.CALL or channel == "call":
            # Calls handled by phone_service, not here
            return True
        else:
            self.logger.error(f"Unknown channel: {channel}")
            return False
    
    async def _send_email(self, lead_data: Dict, message: str) -> bool:
        email = lead_data.get("email")
        if not email:
            return False
        
        try:
            result = await send_email(to_email=email, subject="Response", body=message)
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception as e:
            self.logger.error(f"Email send failed: {e}")
            return False
    
    async def _send_sms(self, lead_data: Dict, message: str) -> bool:
        phone = lead_data.get("phone")
        if not phone:
            return False
        
        try:
            result = await send_sms(to_phone=phone, message=message)
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception as e:
            self.logger.error(f"SMS send failed: {e}")
            return False
    
    async def _send_whatsapp(self, lead_data: Dict, message: str) -> bool:
        phone = lead_data.get("phone")
        if not phone:
            return False
        
        try:
            result = await send_whatsapp(to_phone=phone, message=message)
            return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception as e:
            self.logger.error(f"WhatsApp send failed: {e}")
            return False


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
            return state
        
        self.logger.info("Scheduling callback...")
        
        entities = intelligence.get("entities", {})
        preferred_time = entities.get("preferred_time")
        
        try:
            from datetime import datetime, timedelta
            callback_time = datetime.utcnow() + timedelta(hours=24)
            
            state["callback_scheduled"] = True
            state["callback_time"] = callback_time.isoformat()
            state["completed_actions"].append("schedule_callback")
            
            self.logger.info(f"✓ Callback scheduled for {callback_time}")
        
        except Exception as e:
            self.logger.error(f"Scheduling failed: {e}")
            state["callback_scheduled"] = False
        
        return state


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
            return state
        
        self.logger.info("Verifying lead data...")
        
        lead_data = state.get("lead_data", {})
        issues = []
        
        # Verify email
        email = lead_data.get("email")
        if email and not self._verify_email(email):
            issues.append(f"Invalid email: {email}")
        
        # Verify phone
        phone = lead_data.get("phone")
        if phone and not self._verify_phone(phone):
            issues.append(f"Invalid phone: {phone}")
        
        state["data_verified"] = len(issues) == 0
        state["verification_issues"] = issues
        
        if len(issues) == 0:
            state["completed_actions"].append("verify_data")
            self.logger.info("✓ Data verified")
        else:
            self.logger.warning(f"Verification issues: {issues}")
        
        return state
    
    def _verify_email(self, email: str) -> bool:
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _verify_phone(self, phone: str) -> bool:
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
        """Run all execution agents in parallel"""
        
        self.logger.info("Starting parallel execution...")
        
        tasks = [
            self.communication_agent.execute(state.copy()),
            self.scheduling_agent.execute(state.copy()),
            self.verification_agent.execute(state.copy())
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
                self.logger.error(f"Agent failed: {result}")
                if "errors" not in final_state:
                    final_state["errors"] = []
                final_state["errors"].append({
                    "node": "parallel_executor",
                    "error": str(result)
                })
        
        self.logger.info(
            f"✓ Parallel execution complete - "
            f"Sent: {final_state.get('communication_sent')}, "
            f"Callback: {final_state.get('callback_scheduled')}, "
            f"Verified: {final_state.get('data_verified')}"
        )
        
        return final_state


# Export instances
communication_agent = CommunicationAgent()
scheduling_agent = SchedulingAgent()
verification_agent = VerificationAgent()
parallel_executor = ParallelExecutor()