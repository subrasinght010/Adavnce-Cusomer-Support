# nodes/parallel_execution_agents.py
"""
Parallel Execution Agents - UPDATED for Inbound/Outbound
"""

from typing import Dict

from nodes.core.base_node import BaseNode
from state.workflow_state import OptimizedWorkflowState, ChannelType

# Services
from services.email_service import send_email
from services.sms_service import send_sms
from services.whatsapp_service import send_whatsapp
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

communication_agent = CommunicationAgent()
