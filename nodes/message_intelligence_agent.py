# nodes/message_intelligence_agent.py
"""
Message Intelligence Agent - AI-enhanced template formatting + DB save
"""

from typing import Dict, List
from datetime import datetime
from langchain_core.prompts import PromptTemplate

from nodes.core.base_node import BaseNode
from state.workflow_state import OptimizedWorkflowState
from tools.language_model import llm
from database.db import get_db
from database.crud import DBManager


class MessageIntelligenceAgent(BaseNode):
    """Formats messages with AI personalization + saves to DB"""
    
    def __init__(self):
        super().__init__("message_intelligence")
        self.llm = llm
        
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Process pending sends + save AI response to DB"""
        
        # Process pending sends
        pending = state.get("pending_sends", [])
        
        if pending:
            self.logger.info(f"Processing {len(pending)} pending sends")
            
            conversation_summary = self._build_conversation_summary(
                state.get("conversation_history", [])
            )
            
            for item in pending:
                try:
                    await self._process_pending_send(item, conversation_summary)
                except Exception as e:
                    self.logger.error(f"Failed to send via {item['channel']}: {e}")
            
            state["pending_sends"] = []
            state["communication_sent"] = True
        
        # Save only AI response (webhook already saved incoming)
        await self._save_ai_response(state)
        
        return state
    
    async def _save_incoming_message(self, state: OptimizedWorkflowState):
        """Save user message to DB"""
        try:
            if not state.get("current_message"):
                return
            
            async with get_db() as db:
                db_manager = DBManager(db)
                
                await db_manager.add_conversation(
                    lead_id=int(state.get("lead_id")),
                    message=state["current_message"],
                    channel=str(state.get("channel", "unknown")),
                    sender="user",
                    message_id=state.get("message_id"),
                    intent_detected=state.get("detected_intent")
                )
                
                self.logger.info("✓ Incoming message saved to DB")
        except Exception as e:
            self.logger.error(f"Failed to save incoming message: {e}")
    
    async def _save_ai_response(self, state: OptimizedWorkflowState):
        """Save AI response to DB"""
        try:
            intelligence = state.get("intelligence_output", {})
            response_text = intelligence.get("response_text")
            
            if not response_text:
                return
            
            async with get_db() as db:
                db_manager = DBManager(db)
                
                await db_manager.add_conversation(
                    lead_id=int(state.get("lead_id")),
                    message=response_text,
                    channel=str(state.get("channel", "unknown")),
                    sender="ai",
                    intent_detected=intelligence.get("intent"),
                    cost=state.get("llm_calls_made", 0) * 0.001
                )
                
                self.logger.info("✓ AI response saved to DB")
        except Exception as e:
            self.logger.error(f"Failed to save AI response: {e}")
    
    def _build_conversation_summary(self, history: List[Dict]) -> str:
        """Build conversation context (last 10 messages)"""
        if not history:
            return "No previous conversation"
        
        summary_lines = []
        for msg in history[-10:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_lines.append(f"{role.title()}: {content[:100]}")
        
        return "\n".join(summary_lines)
    
    async def _process_pending_send(self, item: Dict, conversation_summary: str):
        """Send message with AI-personalized intro + static template"""
        
        channel = item["channel"]
        to = item["to"]
        content_type = item["content_type"]
        
        if channel == "email":
            await self._send_email_with_context(to, content_type, conversation_summary)
        elif channel == "sms":
            await self._send_sms_with_context(to, content_type, conversation_summary)
        elif channel == "whatsapp":
            await self._send_whatsapp_with_context(to, content_type, conversation_summary)
    
    async def _send_email_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send email: AI analyzes request → fetches KB content → finds matching files → sends"""
        from services.email_service import send_email_with_attachment
        
        # Step 1: AI understands what user asked for
        specific_request = await self._analyze_user_request(conversation_summary, content_type)
        
        # Step 2: Fetch relevant KB content based on AI analysis
        kb_content = await self._fetch_relevant_content(specific_request, content_type)
        
        # Step 3: Find matching attachment files
        attachment_paths = self._get_attachment_path(content_type, specific_request)
        
        # Step 4: Generate personalized intro
        personalized_intro = await self._generate_intro(
            conversation_summary, content_type, "email"
        )
        
        # Step 5: Build email body
        subject = f"TechCorp {content_type.title()} Information"
        body = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>{subject}</h2>
            
            <p style="color: #333; font-size: 16px; line-height: 1.6;">
                {personalized_intro}
            </p>
            
            <div style="margin: 20px 0;">
                {kb_content}
            </div>
            
            {f"<p style='margin-top: 20px;'>📎 Attached documents: {len(attachment_paths)} file(s)</p>" if attachment_paths else ""}
            
            <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #666; font-size: 12px;">
                This email follows our conversation on {datetime.now().strftime('%B %d, %Y')}
            </p>
        </div>
        """
        
        result = await send_email_with_attachment(
            to=to, 
            subject=subject, 
            body=body,
            attachment_paths=attachment_paths
        )
        self.logger.info(f"✓ Email sent to {to} with {len(attachment_paths)} attachments")
    
    async def _send_sms_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send SMS with AI-summarized content (no files, 160 char limit)"""
        from services.sms_service import send_sms
        
        # AI generates ultra-concise summary from conversation
        specific_request = await self._analyze_user_request(conversation_summary, content_type)
        
        # Fetch KB content
        from tools.vector_store import query_knowledge_base
        kb_results = query_knowledge_base(f"{content_type} {specific_request}", top_k=1, relevance_threshold=0.5)
        
        # AI condenses to SMS-friendly format
        if kb_results:
            sms_text = await self._condense_for_sms(kb_results[0]['content'], content_type)
        else:
            sms_text = self._get_sms_template(content_type)
        
        # Keep under 160 chars
        message = sms_text[:160]
        
        result = await send_sms(to_phone=to, message=message)
        self.logger.info(f"✓ SMS sent to {to}")
    
    async def _send_whatsapp_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send WhatsApp with AI-personalized intro"""
        from services.whatsapp_service import send_whatsapp
        
        # AI generates intro
        intro = await self._generate_intro(
            conversation_summary, content_type, "whatsapp"
        )
        
        # Get template
        template = self._get_whatsapp_template(content_type)
        
        # Combine
        message = f"{intro}\n\n{template}"
        
        result = await send_whatsapp(to_phone=to, message=message)
        self.logger.info(f"✓ WhatsApp sent to {to}")
    
    async def _analyze_user_request(self, conversation: str, content_type: str) -> str:
        """AI extracts what specifically user asked for"""
        
        prompt = PromptTemplate.from_template("""
            Analyze this conversation and extract EXACTLY what the user wants regarding {content_type}.

            Conversation:
            {conversation}

            Output ONLY the specific aspect they're interested in (1-2 keywords).
            Examples:
            - "enterprise plan pricing" → "enterprise"
            - "refund policy" → "refund"
            - "API documentation" → "api"
            - "all product features" → "all"

            Your analysis:""")
                    
        response = await self.llm.ainvoke(
            prompt.format(conversation=conversation[-500:], content_type=content_type)
        )
        
        return response.content.strip().lower()
    
    async def _fetch_relevant_content(self, specific_request: str, content_type: str) -> str:
        """Fetch KB content matching user's specific request"""
        from tools.vector_store import query_knowledge_base
        
        # Search KB with specific request
        query = f"{content_type} {specific_request}"
        kb_results = query_knowledge_base(query, top_k=3, relevance_threshold=0.5)
        
        if kb_results:
            content_html = ""
            for doc in kb_results:
                content_html += f"<div style='margin-bottom: 20px;'>{doc['content']}</div>"
            return content_html
        
        # Fallback to generic template
        return self._get_email_template(content_type)[1]
    
    def _get_attachment_path(self, content_type: str, specific_request: str = None) -> list:
        """Find files matching content_type AND user's specific request"""
        from pathlib import Path
        
        kb_path = Path('knowledge_base')
        files = []
        
        # If user asked for something specific, prioritize matching files
        if specific_request and specific_request != "all":
            # Search for files containing specific keyword
            files.extend(kb_path.glob(f"*{specific_request}*.pdf"))
            files.extend(kb_path.glob(f"{content_type}*{specific_request}*.pdf"))
        
        # Add general files for content_type
        patterns = {
            'pricing': ['pricing*.pdf'],
            'product': ['product*.pdf'],
            'catalog': ['catalog*.pdf'],
            'policy': ['polic*.pdf', 'terms*.pdf']
        }
        
        for pattern in patterns.get(content_type, []):
            files.extend(kb_path.glob(pattern))
        
        # Remove duplicates, return as strings
        return list(set([str(f) for f in files if f.exists()]))
    
    async def _generate_intro(
        self,
        conversation: str,
        content_type: str,
        channel: str
    ) -> str:
        """Use LLM to generate personalized intro based on conversation"""
        
        # Adjust length based on channel
        max_length = {
            "email": "2-3 sentences",
            "sms": "1 short sentence (max 40 chars)",
            "whatsapp": "1-2 sentences"
        }.get(channel, "1-2 sentences")
        
        prompt = PromptTemplate.from_template("""
            Based on this conversation, write a personalized intro for sending {content_type} information via {channel}.

            Conversation Context:
            {conversation}

            Requirements:
            - Length: {max_length}
            - Tone: Professional but friendly
            - Reference what user asked about
            - Natural transition to the content below

            Output ONLY the intro text, nothing else.

            Example for pricing request: "As discussed, here's the detailed pricing breakdown you requested for our Enterprise plan."
            Example for product info: "Following up on your question about our API features, here's the complete documentation."

            Your intro:""")
        
        response = await self.llm.ainvoke(
            prompt.format(
                conversation=conversation[-500:],  # Last 500 chars
                content_type=content_type,
                channel=channel,
                max_length=max_length
            )
        )
        
        return response.content.strip()
    
    async def _condense_for_sms(self, kb_content: str, content_type: str) -> str:
        """AI condenses KB content to 1-2 lines for SMS"""
        
        prompt = PromptTemplate.from_template("""
            Condense this to 1-2 lines for SMS (max 140 chars):

            {content}

            Focus only on key {content_type} details. Be ultra-concise.

            Your SMS text:""")
        
        response = await self.llm.ainvoke(
            prompt.format(content=kb_content[:500], content_type=content_type)
        )
        
        return response.content.strip()
    
    def _get_email_template(self, content_type: str):
        """Fetch template from KB or use static fallback"""
        from tools.vector_store import query_knowledge_base
        
        # Try to get content from KB
        kb_results = query_knowledge_base(content_type, top_k=3, relevance_threshold=0.6)
        
        if kb_results:
            # Use KB content
            kb_content = "\n\n".join([
                f"<div style='margin-bottom: 20px;'>{doc['content']}</div>" 
                for doc in kb_results
            ])
            return (f'TechCorp {content_type.title()} Information', kb_content)
        
        # Fallback to static templates
        templates = {
            'pricing': (
                'TechCorp Pricing Plans',
                '''
                <table style="border-collapse: collapse; width: 100%; margin-top: 20px;">
                    <tr style="background: #f0f0f0;">
                        <th style="padding: 12px; text-align: left;">Plan</th>
                        <th style="padding: 12px; text-align: left;">Price</th>
                        <th style="padding: 12px; text-align: left;">Features</th>
                    </tr>
                    <tr>
                        <td style="padding: 12px;">Basic</td>
                        <td style="padding: 12px;"><strong>$99/month</strong></td>
                        <td style="padding: 12px;">Core features, 10GB storage</td>
                    </tr>
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 12px;">Pro</td>
                        <td style="padding: 12px;"><strong>$199/month</strong></td>
                        <td style="padding: 12px;">Advanced features, 100GB storage, Priority support</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px;">Enterprise</td>
                        <td style="padding: 12px;"><strong>Custom</strong></td>
                        <td style="padding: 12px;">Full suite, Unlimited storage, Dedicated account manager</td>
                    </tr>
                </table>
                <p style="margin-top: 20px;">Visit <a href="https://techcorp.com/pricing">techcorp.com/pricing</a> for full details.</p>
                '''
            ),
            'product': (
                'TechCorp Product Information',
                '''
                <h3>Product Features</h3>
                <ul style="line-height: 1.8;">
                    <li>AI-powered automation</li>
                    <li>Real-time analytics dashboard</li>
                    <li>Multi-channel integration</li>
                    <li>99.9% uptime SLA</li>
                </ul>
                <p>Learn more: <a href="https://techcorp.com/products">techcorp.com/products</a></p>
                '''
            ),
            'policy': (
                'TechCorp Policies',
                '''
                <h3>Our Policies</h3>
                <ul style="line-height: 1.8;">
                    <li><strong>Refund:</strong> 30-day money-back guarantee</li>
                    <li><strong>Shipping:</strong> 5-7 business days standard</li>
                    <li><strong>Support:</strong> 24/7 technical assistance</li>
                    <li><strong>Privacy:</strong> Your data is secure with us</li>
                </ul>
                <p>Full details: <a href="https://techcorp.com/policies">techcorp.com/policies</a></p>
                '''
            )
        }
        return templates.get(content_type, ('TechCorp Information', '<p>Information as requested</p>'))
    
    def _get_sms_template(self, content_type: str):
        """Fallback SMS templates (no KB search, just static)"""
        templates = {
            'pricing': 'Basic $99/mo, Pro $199/mo, Enterprise custom. Details: techcorp.com/pricing',
            'product': 'Product info: techcorp.com/products',
            'policy': 'Policies: techcorp.com/policies'
        }
        return templates.get(content_type, 'Info: techcorp.com')
    
    def _get_whatsapp_template(self, content_type: str):
        """WhatsApp templates - try KB first, fallback to static"""
        from tools.vector_store import query_knowledge_base
        
        # Try KB
        kb_results = query_knowledge_base(content_type, top_k=2, relevance_threshold=0.6)
        if kb_results:
            kb_text = "\n\n".join([doc['content'][:300] for doc in kb_results])
            return f"📄 *{content_type.title()} Information*\n\n{kb_text}\n\n🔗 techcorp.com"
        
        # Static fallback
        templates = {
            'pricing': '''💰 *Pricing Plans*

            ✅ Basic: $99/month
            ✅ Pro: $199/month  
            ✅ Enterprise: Custom

            🔗 techcorp.com/pricing''',
                        
                        'product': '''📦 *Product Info*

            Our platform includes:
            • AI automation
            • Real-time analytics
            • Multi-channel support

            🔗 techcorp.com/products''',
                        
                        'policy': '''📋 *Our Policies*

            • 30-day refund guarantee
            • 5-7 day shipping
            • 24/7 support
            • Secure data privacy

            🔗 techcorp.com/policies'''
                    }
        return templates.get(content_type, '🔗 More info: techcorp.com')


# Singleton
message_intelligence_agent = MessageIntelligenceAgent()
# nodes/message_intelligence_agent.py
"""
Message Intelligence Agent - AI-enhanced template formatting
"""

from typing import Dict, List
from datetime import datetime
from langchain_core.prompts import PromptTemplate

from nodes.core.base_node import BaseNode
from state.workflow_state import OptimizedWorkflowState
from tools.language_model import llm


class MessageIntelligenceAgent(BaseNode):
    """Formats messages with AI personalization + static templates"""
    
    def __init__(self):
        super().__init__("message_intelligence")
        self.llm = llm
        
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Process pending sends with AI-enhanced context"""
        
        pending = state.get("pending_sends", [])
        
        if not pending:
            return state
        
        self.logger.info(f"Processing {len(pending)} pending sends")
        
        # Build conversation context
        conversation_summary = self._build_conversation_summary(
            state.get("conversation_history", [])
        )
        
        # Process each pending send
        for item in pending:
            try:
                await self._process_pending_send(item, conversation_summary)
            except Exception as e:
                self.logger.error(f"Failed to send via {item['channel']}: {e}")
        
        # Clear pending sends
        state["pending_sends"] = []
        state["communication_sent"] = True
        
        return state
    
    def _build_conversation_summary(self, history: List[Dict]) -> str:
        """Build conversation context (last 10 messages)"""
        if not history:
            return "No previous conversation"
        
        summary_lines = []
        for msg in history[-10:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_lines.append(f"{role.title()}: {content[:100]}")
        
        return "\n".join(summary_lines)
    
    async def _process_pending_send(self, item: Dict, conversation_summary: str):
        """Send message with AI-personalized intro + static template"""
        
        channel = item["channel"]
        to = item["to"]
        content_type = item["content_type"]
        
        if channel == "email":
            await self._send_email_with_context(to, content_type, conversation_summary)
        elif channel == "sms":
            await self._send_sms_with_context(to, content_type, conversation_summary)
        elif channel == "whatsapp":
            await self._send_whatsapp_with_context(to, content_type, conversation_summary)
    
    async def _send_email_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send email: AI analyzes request → fetches KB content → finds matching files → sends"""
        from services.email_service import send_email_with_attachment
        
        # Step 1: AI understands what user asked for
        specific_request = await self._analyze_user_request(conversation_summary, content_type)
        
        # Step 2: Fetch relevant KB content based on AI analysis
        kb_content = await self._fetch_relevant_content(specific_request, content_type)
        
        # Step 3: Find matching attachment files
        attachment_paths = self._get_attachment_path(content_type, specific_request)
        
        # Step 4: Generate personalized intro
        personalized_intro = await self._generate_intro(
            conversation_summary, content_type, "email"
        )
        
        # Step 5: Build email body
        subject = f"TechCorp {content_type.title()} Information"
        body = f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>{subject}</h2>
            
            <p style="color: #333; font-size: 16px; line-height: 1.6;">
                {personalized_intro}
            </p>
            
            <div style="margin: 20px 0;">
                {kb_content}
            </div>
            
            {f"<p style='margin-top: 20px;'>📎 Attached documents: {len(attachment_paths)} file(s)</p>" if attachment_paths else ""}
            
            <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #666; font-size: 12px;">
                This email follows our conversation on {datetime.now().strftime('%B %d, %Y')}
            </p>
        </div>
        """
        
        result = await send_email_with_attachment(
            to=to, 
            subject=subject, 
            body=body,
            attachment_paths=attachment_paths
        )
        self.logger.info(f"✓ Email sent to {to} with {len(attachment_paths)} attachments")
    
    async def _analyze_user_request(self, conversation: str, content_type: str) -> str:
        """AI extracts what specifically user asked for"""
        from langchain_core.prompts import PromptTemplate
        
        prompt = PromptTemplate.from_template("""
            Analyze this conversation and extract EXACTLY what the user wants regarding {content_type}.

            Conversation:
            {conversation}

            Output ONLY the specific aspect they're interested in (1-2 keywords).
            Examples:
            - "enterprise plan pricing" → "enterprise"
            - "refund policy" → "refund"
            - "API documentation" → "api"
            - "all product features" → "all"

            Your analysis:""")
        
        response = await self.llm.ainvoke(
            prompt.format(conversation=conversation[-500:], content_type=content_type)
        )
        
        return response.content.strip().lower()
    
    async def _fetch_relevant_content(self, specific_request: str, content_type: str) -> str:
        """Fetch KB content matching user's specific request"""
        from tools.vector_store import query_knowledge_base
        
        # Search KB with specific request
        query = f"{content_type} {specific_request}"
        kb_results = query_knowledge_base(query, top_k=3, relevance_threshold=0.5)
        
        if kb_results:
            content_html = ""
            for doc in kb_results:
                content_html += f"<div style='margin-bottom: 20px;'>{doc['content']}</div>"
            return content_html
        
        # Fallback to generic template
        return self._get_email_template(content_type)[1]
    
    def _get_attachment_path(self, content_type: str, specific_request: str = None) -> list:
        """Find files matching content_type AND user's specific request"""
        from pathlib import Path
        
        kb_path = Path('knowledge_base')
        files = []
        
        # If user asked for something specific, prioritize matching files
        if specific_request and specific_request != "all":
            # Search for files containing specific keyword
            files.extend(kb_path.glob(f"*{specific_request}*.pdf"))
            files.extend(kb_path.glob(f"{content_type}*{specific_request}*.pdf"))
        
        # Add general files for content_type
        patterns = {
            'pricing': ['pricing*.pdf'],
            'product': ['product*.pdf'],
            'catalog': ['catalog*.pdf'],
            'policy': ['polic*.pdf', 'terms*.pdf']
        }
        
        for pattern in patterns.get(content_type, []):
            files.extend(kb_path.glob(pattern))
        
        # Remove duplicates, return as strings
        return list(set([str(f) for f in files if f.exists()]))
    
    async def _send_sms_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send SMS with AI-summarized content (no files, 160 char limit)"""
        from services.sms_service import send_sms
        
        # AI generates ultra-concise summary from conversation
        specific_request = await self._analyze_user_request(conversation_summary, content_type)
        
        # Fetch KB content
        from tools.vector_store import query_knowledge_base
        kb_results = query_knowledge_base(f"{content_type} {specific_request}", top_k=1, relevance_threshold=0.5)
        
        # AI condenses to SMS-friendly format
        if kb_results:
            sms_text = await self._condense_for_sms(kb_results[0]['content'], content_type)
        else:
            sms_text = self._get_sms_template(content_type)
        
        # Keep under 160 chars
        message = sms_text[:160]
        
        result = await send_sms(to_phone=to, message=message)
        self.logger.info(f"✓ SMS sent to {to}")
    
    async def _condense_for_sms(self, kb_content: str, content_type: str) -> str:
        """AI condenses KB content to 1-2 lines for SMS"""
        from langchain_core.prompts import PromptTemplate
        
        prompt = PromptTemplate.from_template("""
            Condense this to 1-2 lines for SMS (max 140 chars):

            {content}

            Focus only on key {content_type} details. Be ultra-concise.

            Your SMS text:""")
        
        response = await self.llm.ainvoke(
            prompt.format(content=kb_content[:500], content_type=content_type)
        )
        
        return response.content.strip()
    
    async def _send_whatsapp_with_context(
        self,
        to: str,
        content_type: str,
        conversation_summary: str
    ):
        """Send WhatsApp with AI-personalized intro"""
        from services.whatsapp_service import send_whatsapp
        
        # AI generates intro
        intro = await self._generate_intro(
            conversation_summary, content_type, "whatsapp"
        )
        
        # Get template
        template = self._get_whatsapp_template(content_type)
        
        # Combine
        message = f"{intro}\n\n{template}"
        
        result = await send_whatsapp(to_phone=to, message=message)
        self.logger.info(f"✓ WhatsApp sent to {to}: {result}")
    
    async def _generate_intro(
        self,
        conversation: str,
        content_type: str,
        channel: str
    ) -> str:
        """Use LLM to generate personalized intro based on conversation"""
        
        # Adjust length based on channel
        max_length = {
            "email": "2-3 sentences",
            "sms": "1 short sentence (max 40 chars)",
            "whatsapp": "1-2 sentences"
        }.get(channel, "1-2 sentences")
        
        prompt = PromptTemplate.from_template("""
            Based on this conversation, write a personalized intro for sending {content_type} information via {channel}.

            Conversation Context:
            {conversation}

            Requirements:
            - Length: {max_length}
            - Tone: Professional but friendly
            - Reference what user asked about
            - Natural transition to the content below

            Output ONLY the intro text, nothing else.

            Example for pricing request: "As discussed, here's the detailed pricing breakdown you requested for our Enterprise plan."
            Example for product info: "Following up on your question about our API features, here's the complete documentation."

            Your intro:""")
        
        response = await self.llm.ainvoke(
            prompt.format(
                conversation=conversation[-500:],  # Last 500 chars
                content_type=content_type,
                channel=channel,
                max_length=max_length
            )
        )
        
        return response.content.strip()
    
    def _get_email_template(self, content_type: str):
        """Fetch template from KB or use static fallback"""
        from tools.vector_store import query_knowledge_base
        
        # Try to get content from KB
        kb_results = query_knowledge_base(content_type, top_k=3, relevance_threshold=0.6)
        
        if kb_results:
            # Use KB content
            kb_content = "\n\n".join([
                f"<div style='margin-bottom: 20px;'>{doc['content']}</div>" 
                for doc in kb_results
            ])
            return (f'TechCorp {content_type.title()} Information', kb_content)
        
        # Fallback to static templates
        templates = {
            'pricing': (
                'TechCorp Pricing Plans',
                '''
                <table style="border-collapse: collapse; width: 100%; margin-top: 20px;">
                    <tr style="background: #f0f0f0;">
                        <th style="padding: 12px; text-align: left;">Plan</th>
                        <th style="padding: 12px; text-align: left;">Price</th>
                        <th style="padding: 12px; text-align: left;">Features</th>
                    </tr>
                    <tr>
                        <td style="padding: 12px;">Basic</td>
                        <td style="padding: 12px;"><strong>$99/month</strong></td>
                        <td style="padding: 12px;">Core features, 10GB storage</td>
                    </tr>
                    <tr style="background: #f9f9f9;">
                        <td style="padding: 12px;">Pro</td>
                        <td style="padding: 12px;"><strong>$199/month</strong></td>
                        <td style="padding: 12px;">Advanced features, 100GB storage, Priority support</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px;">Enterprise</td>
                        <td style="padding: 12px;"><strong>Custom</strong></td>
                        <td style="padding: 12px;">Full suite, Unlimited storage, Dedicated account manager</td>
                    </tr>
                </table>
                <p style="margin-top: 20px;">Visit <a href="https://techcorp.com/pricing">techcorp.com/pricing</a> for full details.</p>
                '''
            ),
            'product': (
                'TechCorp Product Information',
                '''
                <h3>Product Features</h3>
                <ul style="line-height: 1.8;">
                    <li>AI-powered automation</li>
                    <li>Real-time analytics dashboard</li>
                    <li>Multi-channel integration</li>
                    <li>99.9% uptime SLA</li>
                </ul>
                <p>Learn more: <a href="https://techcorp.com/products">techcorp.com/products</a></p>
                '''
            ),
            'policy': (
                'TechCorp Policies',
                '''
                <h3>Our Policies</h3>
                <ul style="line-height: 1.8;">
                    <li><strong>Refund:</strong> 30-day money-back guarantee</li>
                    <li><strong>Shipping:</strong> 5-7 business days standard</li>
                    <li><strong>Support:</strong> 24/7 technical assistance</li>
                    <li><strong>Privacy:</strong> Your data is secure with us</li>
                </ul>
                <p>Full details: <a href="https://techcorp.com/policies">techcorp.com/policies</a></p>
                '''
            )
        }
        return templates.get(content_type, ('TechCorp Information', '<p>Information as requested</p>'))
    
    def _get_sms_template(self, content_type: str):
        """Fallback SMS templates (no KB search, just static)"""
        templates = {
            'pricing': 'Basic $99/mo, Pro $199/mo, Enterprise custom. Details: techcorp.com/pricing',
            'product': 'Product info: techcorp.com/products',
            'policy': 'Policies: techcorp.com/policies'
        }
        return templates.get(content_type, 'Info: techcorp.com')
    
    def _get_whatsapp_template(self, content_type: str):
        """WhatsApp templates - try KB first, fallback to static"""
        from tools.vector_store import query_knowledge_base
        
        # Try KB
        kb_results = query_knowledge_base(content_type, top_k=2, relevance_threshold=0.6)
        if kb_results:
            kb_text = "\n\n".join([doc['content'][:300] for doc in kb_results])
            return f"📄 *{content_type.title()} Information*\n\n{kb_text}\n\n🔗 techcorp.com"
        
        # Static fallback
        templates = {
            'pricing': '''💰 *Pricing Plans*

            ✅ Basic: $99/month
            ✅ Pro: $199/month  
            ✅ Enterprise: Custom

            🔗 techcorp.com/pricing''',
                        
                        'product': '''📦 *Product Info*

            Our platform includes:
            • AI automation
            • Real-time analytics
            • Multi-channel support

            🔗 techcorp.com/products''',
                        
                        'policy': '''📋 *Our Policies*

            • 30-day refund guarantee
            • 5-7 day shipping
            • 24/7 support
            • Secure data privacy

            🔗 techcorp.com/policies'''
                    }
        return templates.get(content_type, '🔗 More info: techcorp.com')


# Singleton
message_intelligence_agent = MessageIntelligenceAgent()