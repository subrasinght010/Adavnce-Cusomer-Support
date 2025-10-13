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
            pending = state.get("pending_sends", [])
    
            if pending:
                self.logger.info(f"Processing {len(pending)} pending sends")
                
                # Get full conversation context
                conversation_summary = self._build_conversation_summary(
                    state.get("conversation_history", [])
                )
                
                # Process each pending send
                for item in pending:
                    try:
                        await self._process_pending_send(item, conversation_summary, state)
                    except Exception as e:
                        self.logger.error(f"Failed to send via {item['channel']}: {e}")
                
                # Clear pending sends
                state["pending_sends"] = []
                state["communication_sent"] = True

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

    def _build_conversation_summary(self, history: List[Dict]) -> str:
        """Build conversation summary for context"""
        if not history:
            return "No previous conversation"
        
        summary_lines = []
        for msg in history[-10:]:  # Last 10 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_lines.append(f"{role.title()}: {content[:100]}")
        
        return "\n".join(summary_lines)
    
    async def _process_pending_send(
        self,
        item: Dict,
        conversation_summary: str,
        state: OptimizedWorkflowState
    ):
        """Send message with full context"""
        
        channel = item["channel"]
        to = item["to"]
        content_type = item["content_type"]
        
        if channel == "email":
            await self._send_email_with_context(to, content_type, conversation_summary)
        elif channel == "sms":
            await self._send_sms_with_context(to, content_type)
        elif channel == "whatsapp":
            await self._send_whatsapp_with_context(to, content_type)

    async def _send_email_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send email with conversation context"""
        from services.email_service import send_email
        
        subject, body_template = self._get_email_template(content_type)
        
        # Add conversation context
        body = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>{subject}</h2>
            {body_template}
            
            <hr style="margin: 30px 0;">
            
            <h3>Conversation Summary</h3>
            <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
    {conversation_summary}
            </pre>
            
            <p style="color: #666; font-size: 12px;">
                This email was sent following our conversation.
            </p>
        </div>
        """
        
        result = await send_email(to=to, subject=subject, body=body)
        self.logger.info(f"Email sent to {to}: {result}")

    async def _send_sms_with_context(self, to: str, content_type: str):
        """Send SMS (no conversation context - too long)"""
        from services.sms_service import send_sms
        
        message = self._get_sms_template(content_type)
        result = await send_sms(to_phone=to, message=message)
        self.logger.info(f"SMS sent to {to}: {result}")

    async def _send_whatsapp_with_context(self, to: str, content_type: str):
        """Send WhatsApp"""
        from services.whatsapp_service import send_whatsapp
        
        message = self._get_whatsapp_template(content_type)
        result = await send_whatsapp(to_phone=to, message=message)
        self.logger.info(f"WhatsApp sent to {to}: {result}")

    def _get_email_template(self, content_type: str):
        """Email templates with HTML"""
        templates = {
            'pricing': (
                'TechCorp Pricing Plans',
                '''
                <h3>Our Pricing Plans</h3>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr style="background: #f0f0f0;">
                        <th style="padding: 10px; text-align: left;">Plan</th>
                        <th style="padding: 10px; text-align: left;">Price</th>
                        <th style="padding: 10px; text-align: left;">Features</th>
                    </tr>
                    <tr>
                        <td style="padding: 10px;">Basic</td>
                        <td style="padding: 10px;">$99/month</td>
                        <td style="padding: 10px;">Core features</td>
                    </tr>
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 10px;">Pro</td>
                        <td style="padding: 10px;">$199/month</td>
                        <td style="padding: 10px;">Advanced features</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px;">Enterprise</td>
                        <td style="padding: 10px;">Custom</td>
                        <td style="padding: 10px;">Full suite</td>
                    </tr>
                </table>
                '''
            ),
            'product': (
                'TechCorp Product Information',
                '<p>Detailed product information attached...</p>'
            ),
            'catalog': (
                'TechCorp Full Catalog',
                '<p>Our complete product catalog is attached.</p>'
            )
        }
        return templates.get(content_type, ('TechCorp Info', '<p>Information as requested</p>'))

    def _get_sms_template(self, content_type: str):
        """SMS templates (160 char limit)"""
        templates = {
            'pricing': 'TechCorp Pricing: Basic $99/mo, Pro $199/mo, Enterprise custom. Details: techcorp.com/pricing',
            'product': 'TechCorp Product info: techcorp.com/products',
            'catalog': 'Full catalog: techcorp.com/catalog'
        }
        return templates.get(content_type, 'Info: techcorp.com')

    def _get_whatsapp_template(self, content_type: str):
        """WhatsApp templates with emojis"""
        templates = {
            'pricing': '''💰 *TechCorp Pricing Plans*

        ✅ Basic: $99/month
        ✅ Pro: $199/month  
        ✅ Enterprise: Custom pricing

        Visit: techcorp.com/pricing''',
                'product': '''📦 *Product Information*

        Check out our products at:
        techcorp.com/products''',
                'catalog': '''📚 *Full Catalog*

        Download our complete catalog:
        techcorp.com/catalog'''
            }
        return templates.get(content_type, 'More info at techcorp.com')
# Singleton instance
message_intelligence_agent = MessageIntelligenceAgent()