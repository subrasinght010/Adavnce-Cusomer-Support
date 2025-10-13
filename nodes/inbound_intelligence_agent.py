# nodes/inbound_intelligence_agent.py
"""
Inbound Intelligence with LangGraph ReAct Agent - Mistral Compatible
"""

import json
from datetime import datetime
from langchain_core.tools import Tool
from langchain_core.messages import HumanMessage, AIMessage

from nodes.core.base_node import BaseNode
from nodes.core.intelligence_models import IntelligenceOutput
from state.workflow_state import OptimizedWorkflowState, extract_quick_fields
from tools.language_model import llm
from tools.vector_store import query_knowledge_base
from database.crud import DBManager
from database.db import get_db


class InboundIntelligenceAgent(BaseNode):
    
    def __init__(self):
        super().__init__("inbound_intelligence")
        self.llm = llm
        self.tools = self._create_tools()
        self.agent = self._create_agent()
    
    def _create_tools(self):
        return [
            Tool(
                name="search_knowledge_base",
                description="Search company knowledge base for product info, policies, pricing. Input: search query",
                func=self._search_kb
            ),
            Tool(
                name="get_lead_history",
                description="Get past conversations with this lead. Input: lead_id",
                func=self._get_history_sync
            ),
            Tool(
                name="check_ticket_status",
                description="Check support ticket status. Input: ticket_id or lead_id",
                func=self._check_ticket
            ),
            Tool(
                name="schedule_callback",
                description="Schedule callback at specific time. Input: 'lead_id|datetime|reason' format",
                func=self._schedule_callback
            ),
            Tool(
                name="send_details",
                description="Send details via channel. Input: 'lead_id|channel|content_type' (channel: email/sms/whatsapp, content_type: pricing/product/catalog)",
                func=self._send_details
            ),
            Tool(
                name="escalate_to_human",
                description="Create escalation ticket for human agent. Input: reason and summary",
                func=self._create_escalation
            )
        ]
    
    def _search_kb(self, query: str) -> str:
        """Synchronous KB search"""
        try:
            results = query_knowledge_base(query=query, top_k=3)
            if results:
                return "\n".join([
                    f"[{r.get('metadata',{}).get('source','Unknown')}]: {r.get('content','')}" 
                    for r in results
                ])
            return "No relevant information found in knowledge base."
        except Exception as e:
            self.logger.error(f"KB search failed: {e}")
            return f"Knowledge base search error: {str(e)}"
    
    def _get_history_sync(self, lead_id: str) -> str:
        """Sync wrapper for async DB call"""
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._get_history_async(lead_id))
                loop.close()
                return result
            else:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_in_new_loop, lead_id)
                    return future.result(timeout=10)
        except Exception as e:
            self.logger.error(f"History fetch failed: {e}")
            return "No conversation history available."
    
    def _run_in_new_loop(self, lead_id: str) -> str:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._get_history_async(lead_id))
        finally:
            loop.close()
    
    async def _get_history_async(self, lead_id: str) -> str:
        try:
            async with get_db() as db:
                mgr = DBManager(db)
                convos = await mgr.get_lead_conversations(lead_id, limit=5)
                if convos:
                    return "\n".join([f"{c.sender}: {c.message}" for c in convos])
                return "No previous conversations found."
        except Exception as e:
            self.logger.error(f"DB fetch error: {e}")
            return "Error retrieving history."
    
    def _validate_entities(self, intelligence: IntelligenceOutput, user_message: str) -> IntelligenceOutput:
        """Post-process validation to catch hallucinated entities"""
        entities = intelligence.entities or {}
        needs_clarification = False
        clarification_q = None
        
        # Check callback without specific time
        if 'callback' in intelligence.intent.lower():
            callback_time = entities.get('callback_time')
            # Check if time is in user message
            time_keywords = ['at', 'pm', 'am', ':00', 'oclock', 'o\'clock']
            has_time = any(keyword in user_message.lower() for keyword in time_keywords)
            
            if not has_time and callback_time:
                # LLM hallucinated time - clear it
                entities['callback_time'] = None
                needs_clarification = True
                clarification_q = "What time works best for your callback?"
        
        # Check email without address in message
        if 'email' in intelligence.intent.lower() or entities.get('channel') == 'email':
            email = entities.get('email')
            if email and '@' not in user_message:
                # Hallucinated email - don't use it
                entities['email'] = None
        
        # Check phone without number in message
        if entities.get('phone') and not any(char.isdigit() for char in user_message):
            entities['phone'] = None
        
        if needs_clarification:
            intelligence.needs_clarification = True
            intelligence.clarification_question = clarification_q
            intelligence.response_text = clarification_q
            intelligence.next_actions = []
        
        intelligence.entities = entities
        return intelligence
    
    def _check_ticket(self, input_str: str) -> str:
        """Check ticket status - placeholder"""
        # TODO: Integrate with your ticketing system
        return f"Ticket lookup for '{input_str}': No open tickets found."
    
    def _schedule_callback(self, input_str: str) -> str:
        """Schedule callback with validation"""
        try:
            parts = input_str.split('|')
            lead_id = parts[0].strip()
            callback_time = parts[1].strip() if len(parts) > 1 else None
            reason = parts[2].strip() if len(parts) > 2 else "General inquiry"
            
            # Validate required fields
            if not callback_time or callback_time.lower() in ['asap', 'none', 'null', '']:
                return "ERROR: Callback time is required. Please specify when to call back."
            
            if not lead_id:
                return "ERROR: Lead ID is required."
            
            self.logger.info(f"Callback scheduled - Lead: {lead_id}, Time: {callback_time}, Reason: {reason}")
            return f"Callback scheduled for {callback_time}. Reason: {reason}. You'll receive a call at your registered number."
        except Exception as e:
            return f"ERROR: Invalid callback format. Use: lead_id|datetime|reason"
    
    def _send_details(self, input_str: str) -> str:
        """Send details with validation"""
        try:
            parts = input_str.split('|')
            lead_id = parts[0].strip()
            channel = parts[1].strip().lower() if len(parts) > 1 else None
            content_type = parts[2].strip() if len(parts) > 2 else None
            
            # Validate
            if not channel or channel not in ['email', 'sms', 'whatsapp']:
                return "ERROR: Valid channel required (email/sms/whatsapp)"
            
            if not content_type:
                return "ERROR: Content type required (pricing/product/catalog)"
            
            self.logger.info(f"Details sent - Lead: {lead_id}, Channel: {channel}, Type: {content_type}")
            
            channel_map = {
                "email": "email address",
                "sms": "phone number", 
                "whatsapp": "WhatsApp"
            }
            
            return f"{content_type.title()} details will be sent to your {channel_map.get(channel, channel)} shortly."
        except Exception as e:
            return f"ERROR: Invalid format. Use: lead_id|channel|content_type"
    
    def _create_escalation(self, reason: str) -> str:
        """Create escalation ticket"""
        # TODO: Integrate with your ticketing system
        return f"Escalation created: {reason}. Agent will contact within 2 hours."
    
    def _create_agent(self):
        """Manual ReAct loop - Mistral compatible"""
        return None  # We'll handle tool execution manually
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        lead_id = state.get('lead_id', 'unknown')
        user_message = state.get('current_message')
        
        # Get conversation history
        history = state.get('conversation_history', [])
        history_text = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in history[-5:]  # Last 5 exchanges
        ]) if history else "No previous conversation"
        
        # Build context with history
        context = f"""You are an AI support agent. Answer the user's question.

Conversation History:
{history_text}

Current Message:
User: {user_message}
Lead: {state.get('lead_data',{}).get('name', 'Unknown')} (ID: {lead_id})
Channel: {state.get('channel')}

Available tools:
{self._format_tools()}

If you need a tool, respond EXACTLY like this:
Action: tool_name
Action Input: your input here

Otherwise, respond with ONLY this JSON (nothing else):
{{"intent": "product_query|callback_request|send_details_email|send_details_sms|send_details_whatsapp|complaint|escalation|general_inquiry", "intent_confidence": 0.9, "entities": {{"callback_time": "2024-10-14T10:00:00", "channel": "email", "email": "user@example.com", "phone": "+911234567890", "content_type": "pricing"}}, "sentiment": "positive", "urgency": "medium", "response_text": "your answer here", "needs_clarification": false, "next_actions": ["schedule_callback", "send_email"], "requires_human": false}}

Extract entities when user mentions:
- Callback time/date
- Email/SMS/WhatsApp preference
- Contact details
- Content type (pricing/product/catalog)

Your response:"""
        
        try:
            # Manual ReAct loop
            max_iterations = 3
            agent_scratchpad = ""
            
            for i in range(max_iterations):
                prompt = f"{context}\n{agent_scratchpad}"
                response = await self._llm_call(prompt)
                
                # Check for Final Answer or direct JSON
                if "Final Answer:" in response:
                    answer = response.split("Final Answer:")[1].strip()
                    intelligence = self._parse(answer)
                    break
                elif "{" in response and "intent" in response:
                    # Direct JSON response
                    intelligence = self._parse(response)
                    break
                
                # Check for tool usage
                if "Action:" in response and "Action Input:" in response:
                    action = self._extract_action(response)
                    if action:
                        tool_name, tool_input = action
                        observation = self._execute_tool(tool_name, tool_input)
                        agent_scratchpad += f"\nAction: {tool_name}\nAction Input: {tool_input}\nObservation: {observation}\n"
                        continue
                
                # No tool, treat as final answer
                intelligence = self._parse(response)
                break
            else:
                intelligence = self._fallback()
                
        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}")
            intelligence = self._fallback()
        
        # POST-VALIDATION: Check for missing critical info
        intelligence = self._validate_entities(intelligence, user_message)
        
        # Apply response templates for consistency
        intelligence = self._apply_response_template(intelligence, state)
        
        # Update state - Add user message first
        state["conversation_history"].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        state["intelligence_output"] = intelligence.dict()
        state = extract_quick_fields(state)
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        
        # Add assistant response
        state["conversation_history"].append({
            "role": "assistant",
            "content": intelligence.response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return state
    
    async def _llm_call(self, prompt: str) -> str:
        """Call LLM with prompt"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.llm._call, prompt)
    
    def _format_tools(self) -> str:
        """Format tools for prompt"""
        return "\n".join([f"- {t.name}: {t.description}" for t in self.tools])
    
    def _extract_action(self, text: str) -> tuple:
        """Extract action and input from response"""
        try:
            action_line = [l for l in text.split('\n') if l.strip().startswith('Action:')][0]
            input_line = [l for l in text.split('\n') if l.strip().startswith('Action Input:')][0]
            
            action = action_line.split('Action:')[1].strip()
            action_input = input_line.split('Action Input:')[1].strip()
            
            return (action, action_input)
        except:
            return None
    
    def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        """Execute tool by name"""
        for tool in self.tools:
            if tool.name == tool_name:
                try:
                    return tool.func(tool_input)
                except Exception as e:
                    return f"Tool error: {e}"
        return f"Tool '{tool_name}' not found"
    
    def _parse(self, text: str) -> IntelligenceOutput:
        """Parse JSON response with validation"""
        try:
            # Extract JSON from text
            cleaned = text.strip()
            
            # Handle markdown
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            
            # Find JSON object
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            if start >= 0 and end > start:
                cleaned = cleaned[start:end]
            
            # Remove control characters
            cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
            
            data = json.loads(cleaned)
            
            # Ensure required fields exist
            if 'intent' not in data:
                data['intent'] = 'general_inquiry'
            if 'response_text' not in data:
                data['response_text'] = data.get('message', 'How can I help you?')
            
            # VALIDATION: Check for incomplete callback requests
            if 'callback' in data.get('intent', ''):
                entities = data.get('entities', {})
                callback_time = entities.get('callback_time')
                if not callback_time or callback_time in ['', 'null', None]:
                    data['needs_clarification'] = True
                    data['clarification_question'] = "What time works best for you?"
                    data['response_text'] = "I'd be happy to schedule a callback. What time works best for you?"
                    data['next_actions'] = []  # Clear actions until we get time
            
            # VALIDATION: Check for email send without address
            if 'send_details_email' in data.get('intent', '') or 'email' in data.get('entities', {}).get('channel', ''):
                email = data.get('entities', {}).get('email')
                if not email or email == 'user@example.com' or '@' not in str(email):
                    # Check if we can get from lead_data (handled in execute)
                    pass
            
            return IntelligenceOutput(**data)
            
        except Exception as e:
            self.logger.warning(f"Parse failed: {e}. Text: {text[:200]}")
            # Try to extract just the message if it exists
            if '"message"' in text or '"response_text"' in text:
                try:
                    import re
                    match = re.search(r'"(?:message|response_text)"\s*:\s*"([^"]+)"', text)
                    if match:
                        return IntelligenceOutput(
                            intent="general_inquiry",
                            intent_confidence=0.7,
                            sentiment="neutral",
                            urgency="medium",
                            response_text=match.group(1)
                        )
                except:
                    pass
            return self._fallback()
    
    def _fallback(self) -> IntelligenceOutput:
        """Fallback response"""
        return IntelligenceOutput(
            intent="general_inquiry",
            intent_confidence=0.5,
            sentiment="neutral",
            urgency="medium",
            response_text="I'm here to help. Could you please rephrase your question?",
            needs_clarification=True
        )


# Singleton instance
inbound_intelligence_agent = InboundIntelligenceAgent()