# nodes/message_intelligence_agent.py
"""
Message Intelligence Agent - Formats and optimizes messages for each channel
"""

import json
from typing import Dict, List, Optional
from datetime import datetime

from nodes.core.base_node import BaseNode
from state.workflow_state import OptimizedWorkflowState, ChannelType, DirectionType
from tools.language_model import llm


class MessageIntelligenceAgent(BaseNode):
    """Transforms raw intelligence output into channel-optimized messages"""
    
    def __init__(self):
        super().__init__("message_intelligence")
        self.llm = llm
        
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Format message based on channel and direction"""
        
        intelligence = state.get("intelligence_output", {})
        raw_text = intelligence.get("response_text", "")
        
        if not raw_text:
            self.logger.warning("No text to format")
            return state
        
        channel = state.get("channel")
        direction = state.get("direction")
        lead_data = state.get("lead_data", {})
        conversation_history = state.get("conversation_history", [])
        
        self.logger.info(f"Formatting {direction} message for {channel}")
        
        try:
            # Detect if this is a reply/follow-up
            is_reply = len(conversation_history) > 0
            
            # Format based on channel
            if channel == ChannelType.EMAIL:
                formatted = await self._format_email(
                    raw_text, lead_data, direction, intelligence, is_reply, conversation_history
                )
            elif channel == ChannelType.SMS:
                formatted = self._format_sms(raw_text, lead_data)
            elif channel == ChannelType.WHATSAPP:
                formatted = self._format_whatsapp(raw_text, lead_data)
            else:
                formatted = {"text": raw_text}
            
            # Update intelligence output with formatted version
            intelligence["response_text"] = formatted.get("text") or formatted.get("body_text")
            intelligence["formatted_message"] = formatted
            state["intelligence_output"] = intelligence
            
            self.logger.info("✓ Message formatted")
            
        except Exception as e:
            self.logger.error(f"Formatting failed: {e}")
            # Keep original text on failure
        
        return state
    
    async def _format_email(
        self, 
        raw_text: str, 
        lead_data: Dict, 
        direction: DirectionType,
        intelligence: Dict
    ) -> Dict:
        """Format for email with subject, HTML, and personalization"""
        
        name = lead_data.get("name", "there")
        intent = intelligence.get("intent", "general")
        
        # Generate subject line
        if direction == DirectionType.INBOUND:
            subject = await self._generate_subject_inbound(intent, raw_text)
        else:
            call_type = intelligence.get("call_type", "follow_up")
            subject = await self._generate_subject_outbound(call_type, lead_data)
        
        # Create HTML body
        body_html = self._create_html_template(name, raw_text, direction)
        
        # Plain text fallback
        body_text = f"Hi {name},\n\n{raw_text}\n\nBest regards,\nTechCorp Team"
        
        return {
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "text": body_text  # For communication agent
        }
    
    async def _generate_subject_inbound(self, intent: str, text: str) -> str:
        """Generate email subject for inbound responses"""
        
        subject_map = {
            "product_query": "Product Information - TechCorp",
            "pricing_query": "Pricing Details - TechCorp",
            "callback_request": "Callback Scheduled - TechCorp",
            "complaint": "We're Here to Help - TechCorp",
            "technical_support": "Technical Support - TechCorp"
        }
        
        # Use mapping or generate with LLM
        if intent in subject_map:
            return subject_map[intent]
        
        # LLM fallback for custom subjects
        try:
            prompt = f"""Generate a concise, professional email subject (max 50 chars) for this response:
            "{text[:100]}..."

            Subject:"""
            subject = await self.llm.agenerate([prompt], max_tokens=20)
            return subject[0][0].text.strip().strip('"')[:50]
        except:
            return "Re: Your Inquiry - TechCorp"
    
    async def _generate_subject_outbound(self, call_type: str, lead_data: Dict) -> str:
        """Generate email subject for outbound campaigns"""
        
        company = lead_data.get("company", "")
        name = lead_data.get("name", "")
        
        # Cold email subjects with personalization
        templates = {
            "cold": [
                f"Quick question about {company}" if company else "Quick question",
                f"Idea for {name}",
                "Worth a conversation?"
            ],
            "warm": [
                f"Following up - {company}" if company else "Following up",
                f"Checking back in"
            ],
            "hot": [
                "Ready when you are",
                "Let's move forward"
            ],
            "follow_up": [
                "Just checking in",
                f"Re: Our conversation"
            ]
        }
        
        subjects = templates.get(call_type, templates["follow_up"])
        return subjects[0]  # Can implement A/B testing here
    
    def _create_html_template(self, name: str, content: str, direction: DirectionType) -> str:
        """Create responsive HTML email template"""
        
        # Add signature based on direction
        if direction == DirectionType.OUTBOUND:
            signature = """
            <p>Best regards,<br>
            <strong>Sales Team</strong><br>
            TechCorp<br>
            <a href="mailto:sales@techcorp.com">sales@techcorp.com</a></p>
            """
        else:
            signature = """
            <p>Best regards,<br>
            <strong>Support Team</strong><br>
            TechCorp<br>
            <a href="mailto:support@techcorp.com">support@techcorp.com</a></p>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h2 style="color: white; margin: 0;">TechCorp</h2>
            </div>
            
            <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px;">Hi {name},</p>
                
                <div style="background: white; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    {self._format_paragraphs(content)}
                </div>
                
                {signature}
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                
                <p style="font-size: 12px; color: #666; text-align: center;">
                    © 2025 TechCorp. All rights reserved.<br>
                    <a href="#" style="color: #667eea; text-decoration: none;">Unsubscribe</a>
                </p>
            </div>
        </body>
        </html>
        """
    
    def _format_paragraphs(self, text: str) -> str:
        """Convert plain text to HTML paragraphs"""
        paragraphs = text.split('\n\n')
        return ''.join(f'<p style="margin: 10px 0;">{p.strip()}</p>' for p in paragraphs if p.strip())
    
    def _format_sms(self, raw_text: str, lead_data: Dict) -> Dict:
        """Format for SMS (160 char limit)"""
        
        # Truncate and add brand
        max_length = 145  # Reserve 15 chars for signature
        
        if len(raw_text) > max_length:
            truncated = raw_text[:max_length-3] + "..."
        else:
            truncated = raw_text
        
        # Add signature
        formatted = f"{truncated} -TechCorp"
        
        return {
            "text": formatted,
            "length": len(formatted)
        }
    
    def _format_whatsapp(self, raw_text: str, lead_data: Dict) -> Dict:
        """Format for WhatsApp with emojis and structure"""
        
        name = lead_data.get("name", "there")
        
        # Add friendly emoji and structure
        formatted = f"👋 Hi {name}!\n\n{raw_text}\n\nNeed help? Just reply here! 💬"
        
        return {
            "text": formatted
        }


# Singleton instance
message_intelligence_agent = MessageIntelligenceAgent()