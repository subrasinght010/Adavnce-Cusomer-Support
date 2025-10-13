# nodes/communication_agent.py
"""
Communication Agent - Updated to use formatted messages
"""

from typing import Dict
from nodes.core.base_node import BaseNode
from state.workflow_state import OptimizedWorkflowState, ChannelType
from services.email_service import send_email
from services.sms_service import send_sms
from services.whatsapp_service import send_whatsapp


class CommunicationAgent(BaseNode):
    """Send messages via any channel using formatted content"""
    
    def __init__(self):
        super().__init__("communication_agent")
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Send communication via channel"""
        
        intelligence = state.get("intelligence_output", {})
        formatted_msg = intelligence.get("formatted_message", {})
        response_text = intelligence.get("response_text", "")
        
        if not response_text:
            self.logger.warning("No response text to send")
            return state
        
        channel = state.get("channel")
        lead_data = state.get("lead_data", {})
        direction = state.get("direction")
        
        self.logger.info(f"[{direction}] Sending via {channel}")
        
        try:
            # Use formatted message if available
            success = await self._send_message(
                channel, 
                lead_data, 
                formatted_msg if formatted_msg else {"text": response_text}
            )
            
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
    
    async def _send_message(
        self, 
        channel: ChannelType, 
        lead_data: Dict, 
        formatted_msg: Dict
    ) -> bool:
        """Route to correct service with formatted content"""
        
        # Normalize to enum if string
        if isinstance(channel, str):
            try:
                channel = ChannelType(channel)
            except ValueError:
                self.logger.error(f"Unknown channel: {channel}")
                return False
        
        if channel == ChannelType.EMAIL:
            return await self._send_email(lead_data, formatted_msg)
        elif channel == ChannelType.SMS:
            return await self._send_sms(lead_data, formatted_msg)
        elif channel == ChannelType.WHATSAPP:
            return await self._send_whatsapp(lead_data, formatted_msg)
        elif channel == ChannelType.CALL:
            return True
        else:
            self.logger.error(f"Unknown channel: {channel}")
            return False
    
    async def _send_email(self, lead_data: Dict, formatted_msg: Dict) -> bool:
        """Send formatted email with thread support"""
        email = lead_data.get("email")
        if not email:
            self.logger.error("No email address")
            return False
        
        try:
            # Use formatted email fields
            subject = formatted_msg.get("subject", "Message from TechCorp")
            body = formatted_msg.get("body_html") or formatted_msg.get("body_text") or formatted_msg.get("text")
            
            # Thread support
            thread_id = formatted_msg.get("thread_id")
            reply_to_id = formatted_msg.get("reply_to_message_id")
            
            result = await send_email(
                to=email,
                subject=subject,
                body=body,
                thread_id=thread_id,
                reply_to_message_id=reply_to_id
            )
            
            return result if isinstance(result, bool) else result.get("success", False)
            
        except Exception as e:
            self.logger.error(f"Email send failed: {e}")
            return False
    
    async def _send_sms(self, lead_data: Dict, formatted_msg: Dict) -> bool:
        """Send formatted SMS"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number")
            return False
        
        try:
            # SMS is pre-formatted with length limit
            message = formatted_msg.get("text", "")
            
            result = await send_sms(to_phone=phone, message=message)
            return result if isinstance(result, bool) else result.get("success", False)
            
        except Exception as e:
            self.logger.error(f"SMS send failed: {e}")
            return False
    
    async def _send_whatsapp(self, lead_data: Dict, formatted_msg: Dict) -> bool:
        """Send formatted WhatsApp message"""
        phone = lead_data.get("phone")
        if not phone:
            self.logger.error("No phone number")
            return False
        
        try:
            message = formatted_msg.get("text", "")
            
            result = await send_whatsapp(to_phone=phone, message=message)
            return result if isinstance(result, bool) else result.get("success", False)
            
        except Exception as e:
            self.logger.error(f"WhatsApp send failed: {e}")
            return False


communication_agent = CommunicationAgent()