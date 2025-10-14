"""
Base Intelligence Agent - Shared logic for all agents
Supports multi-intent detection, entity extraction, and ReAct loop
"""

import json
import re
import asyncio
from datetime import datetime
from abc import abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from langchain_core.tools import Tool

from nodes.core.base_node import BaseNode
from nodes.core.intelligence_models import IntelligenceOutput
from state.workflow_state import OptimizedWorkflowState, extract_quick_fields
from prompts.robust_system_prompts import validate_intent, get_action_for_intent, VALID_INTENTS


class BaseIntelligenceAgent(BaseNode):
    """Base class for intelligence agents with ReAct loop"""
    
    def __init__(self, name: str, llm):
        super().__init__(name)
        self.llm = llm
        self.tools = self._create_tools()
        self._pending_sends = []
    
    # ========================================================================
    # ABSTRACT METHODS - Must be implemented by subclasses
    # ========================================================================
    
    @abstractmethod
    def _create_tools(self) -> List[Tool]:
        """Override to define agent-specific tools"""
        pass
    
    @abstractmethod
    def _get_system_prompt(self, **kwargs) -> str:
        """Override to define agent-specific prompt"""
        pass
    
    @abstractmethod
    def _extract_prompt_vars(self, state: dict) -> dict:
        """Override to extract variables needed for prompt from state"""
        pass
    
    # ========================================================================
    # MAIN EXECUTION
    # ========================================================================
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Main execution with ReAct loop"""
        self._pending_sends = []
        start_time = datetime.utcnow()

        user_message = state.get('current_message', '')
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Executing {self.name} for: {user_message[:50]}...")
        
        # Build context
        try:
            context = self._build_context(state)
            self.logger.debug("✓ Context built successfully")
        except Exception as e:
            self.logger.error(f"Context build failed: {e}", exc_info=True)
            return self._handle_error(state, "context_build_error", str(e))
        
        # ReAct loop
        try:
            intelligence = await self._react_loop(context, max_iterations=3)
            self.logger.info(f"✓ ReAct loop completed")
            
            # Post-process (entity extraction, validation)
            intelligence = self._post_process(intelligence, user_message, state)
            
            self.logger.info(f"✓ Final Output:")
            self.logger.info(f"  - Intents: {intelligence.intents}")
            self.logger.info(f"  - Confidence: {intelligence.intent_confidence:.2f}")
            self.logger.info(f"  - Actions: {intelligence.next_actions}")
            self.logger.info(f"  - Entities: {intelligence.entities}")
            
        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            intelligence = self._fallback(user_message)
        
        # Update state with results
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        state = self._update_state(state, user_message, intelligence, execution_time)
        
        # Handle pending sends
        if self._pending_sends:
            if "pending_sends" not in state:
                state["pending_sends"] = []
            state["pending_sends"].extend(self._pending_sends)
            self.logger.info(f"✓ {len(self._pending_sends)} pending sends queued")
        
        self.logger.info(f"{'='*60}")
        return state
    
    # ========================================================================
    # CONTEXT BUILDING
    # ========================================================================
    
    def _build_context(self, state: dict) -> str:
        """Build prompt context with history and tools"""
        history = self._format_history(state.get('conversation_history', []))
        prompt_kwargs = self._extract_prompt_vars(state)
        
        return self._get_system_prompt(
            conversation_history=history,
            tools_description=self._format_tools(),
            **prompt_kwargs
        )
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        if not history:
            return "(No previous conversation)"
        
        formatted = []
        for turn in history[-5:]:  # Last 5 turns
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')
            timestamp = turn.get('timestamp', '')
            
            if role == 'user':
                formatted.append(f"User: {content}")
            else:
                formatted.append(f"Assistant: {content}")
        
        return "\n".join(formatted)
    
    def _format_tools(self) -> str:
        """Format tool descriptions"""
        if not self.tools:
            return "(No tools available)"
        
        descriptions = []
        for tool in self.tools:
            descriptions.append(f"- {tool.name}: {tool.description}")
        
        return "\n".join(descriptions)
    
    # ========================================================================
    # REACT LOOP
    # ========================================================================
    
    async def _react_loop(self, context: str, max_iterations: int) -> IntelligenceOutput:
        """ReAct reasoning loop with tool execution"""
        self.logger.info(f"Starting ReAct loop (max {max_iterations} iterations)")
        scratchpad = ""
        
        for iteration in range(max_iterations):
            self.logger.debug(f"--- Iteration {iteration + 1}/{max_iterations} ---")
            
            # Get LLM response
            response = await self._llm_call(context + scratchpad)
            self.logger.debug(f"LLM response ({len(response)} chars): {response[:150]}...")
            
            # Check if we have a final answer
            if self._is_final_answer(response):
                self.logger.info(f"✓ Found final answer at iteration {iteration + 1}")
                answer = self._extract_final_answer(response)
                return self._parse(answer)
            
            # Check if LLM wants to use a tool
            if self._has_tool_action(response):
                action = self._extract_action(response)
                if action:
                    tool_name, tool_input = action
                    self.logger.info(f"→ Executing tool: {tool_name}")
                    self.logger.debug(f"  Input: {tool_input[:100]}...")
                    
                    observation = self._execute_tool(tool_name, tool_input)
                    
                    self.logger.info(f"← Tool result: {observation[:100]}...")
                    scratchpad += f"\nAction: {tool_name}\nAction Input: {tool_input}\nObservation: {observation}\n"
                    continue
                else:
                    self.logger.warning("Tool action format detected but couldn't extract action")
            
            # No tool action and no final answer - try to parse as final answer
            self.logger.info("No tool action found, attempting to parse as final answer")
            return self._parse(response)
        
        self.logger.warning("⚠ Max iterations reached without final answer")
        return self._fallback()
    
    def _is_final_answer(self, response: str) -> bool:
        """Check if response contains final answer"""
        return "Final Answer:" in response or (
            "{" in response and 
            ("intents" in response or "intent" in response) and
            "response_text" in response
        )
    
    def _extract_final_answer(self, response: str) -> str:
        """Extract final answer from response"""
        if "Final Answer:" in response:
            return response.split("Final Answer:")[1].strip()
        return response
    
    def _has_tool_action(self, response: str) -> bool:
        """Check if response contains tool action"""
        return "Action:" in response and "Action Input:" in response
    
    # ========================================================================
    # LLM INTERACTION
    # ========================================================================
    
    async def _llm_call(self, prompt: str) -> str:
        """Call LLM with error handling"""
        try:
            if asyncio.iscoroutinefunction(self.llm.invoke):
                response = await self.llm.invoke(prompt)
            else:
                response = self.llm.invoke(prompt)
            
            # Handle different response types
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, dict):
                return response.get('content', str(response))
            else:
                return str(response)
                
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}", exc_info=True)
            raise
    
    # ========================================================================
    # TOOL EXECUTION
    # ========================================================================
    
    def _extract_action(self, response: str) -> Optional[Tuple[str, str]]:
        """Extract tool name and input from response"""
        try:
            # Parse Action and Action Input
            action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
            input_match = re.search(r'Action Input:\s*(.+?)(?:\n|$)', response, re.IGNORECASE | re.DOTALL)
            
            if action_match and input_match:
                tool_name = action_match.group(1).strip()
                tool_input = input_match.group(1).strip()
                return (tool_name, tool_input)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Action extraction failed: {e}")
            return None
    
    def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        """Execute a tool by name"""
        try:
            # Find the tool
            tool = next((t for t in self.tools if t.name == tool_name), None)
            
            if not tool:
                available = [t.name for t in self.tools]
                self.logger.warning(f"Tool '{tool_name}' not found. Available: {available}")
                return f"Error: Tool '{tool_name}' not found. Available tools: {', '.join(available)}"
            
            # Execute the tool
            result = tool.func(tool_input)
            
            # Handle async tools
            if asyncio.iscoroutine(result):
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're already in async context, create new thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self._run_async_tool, result)
                        result = future.result(timeout=30)
                else:
                    result = loop.run_until_complete(result)
            
            return str(result)
            
        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            return f"Error executing tool: {str(e)}"
    
    def _run_async_tool(self, coro):
        """Run async tool in new event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    # ========================================================================
    # RESPONSE PARSING
    # ========================================================================
    
    def _parse(self, response: str) -> IntelligenceOutput:
        """Parse LLM response with multi-intent support"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                self.logger.warning("No JSON found in response, using fallback")
                return self._fallback()
            
            json_str = json_match.group()
            
            # Clean up JSON (remove markdown code blocks)
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON
            data = json.loads(json_str)
            self.logger.debug(f"Parsed JSON: {json.dumps(data, indent=2)}")
            
            # Handle both single and multiple intents
            intents = self._extract_intents(data)
            
            # Validate intents
            valid_intents = [i for i in intents if validate_intent(i)]
            if not valid_intents:
                self.logger.warning(f"No valid intents found in {intents}, using general_inquiry")
                valid_intents = ["general_inquiry"]
            
            # Extract entities
            entities = data.get("entities", {})
            
            # Map intents to actions (if not explicitly provided)
            next_actions = data.get("next_actions")
            if not next_actions:
                next_actions = self._intents_to_actions(valid_intents, entities)
            
            # Build IntelligenceOutput
            intelligence = IntelligenceOutput(
                intent=valid_intents[0],  # Primary intent
                intents=valid_intents,    # All intents
                intent_confidence=float(data.get("intent_confidence", 0.8)),
                entities=entities,
                sentiment=data.get("sentiment", "neutral"),
                urgency=data.get("urgency", "medium"),
                response_text=data.get("response_text", ""),
                needs_clarification=bool(data.get("needs_clarification", False)),
                clarification_question=data.get("clarification_question"),
                next_actions=next_actions,
                requires_human=bool(data.get("requires_human", False)),
                used_knowledge_base=bool(data.get("used_knowledge_base", False))
            )
            
            return intelligence
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            self.logger.error(f"Raw response: {response[:300]}")
            return self._fallback()
        except Exception as e:
            self.logger.error(f"Parse error: {e}", exc_info=True)
            return self._fallback()
    
    def _extract_intents(self, data: dict) -> List[str]:
        """Extract intents from parsed JSON (handle both formats)"""
        # Try new format first
        intents = data.get("intents", [])
        if intents:
            return intents if isinstance(intents, list) else [intents]
        
        # Fallback to old format
        intent = data.get("intent", "general_inquiry")
        
        # Handle pipe-separated format (greeting|product_query)
        if isinstance(intent, str) and "|" in intent:
            return [i.strip() for i in intent.split("|")]
        
        return [intent] if intent else ["general_inquiry"]
    
    # ========================================================================
    # INTENT TO ACTION MAPPING
    # ========================================================================
    
    def _intents_to_actions(self, intents: List[str], entities: dict) -> List[str]:
        """Convert intents to executable actions based on available entities"""
        actions = []
        
        for intent in intents:
            action = self._map_single_intent(intent, entities)
            if action:
                actions.append(action)
        
        return actions
    
    def _map_single_intent(self, intent: str, entities: dict) -> Optional[str]:
        """Map single intent to action"""
        
        # Callback - needs time
        if intent == "callback_request":
            if entities.get("callback_time"):
                return "schedule_callback"
            # else: needs clarification, no action
        
        # Email - needs email address
        elif intent == "send_details_email":
            if entities.get("email") or entities.get("channel") == "email":
                return "send_email"
        
        # SMS - can use lead's phone
        elif intent == "send_details_sms":
            return "send_sms"
        
        # WhatsApp - can use lead's phone
        elif intent == "send_details_whatsapp":
            return "send_whatsapp"
        
        # Complaint - always escalate
        elif intent == "complaint":
            return "escalate_to_human"
        
        # No action for query intents
        return None
    
    # ========================================================================
    # ENTITY EXTRACTION
    # ========================================================================
    
    def _extract_entities_from_context(self, state: dict) -> dict:
        """Extract entities from current message + conversation history"""
        entities = {}
        
        current_msg = state.get('current_message', '').lower()
        
        # Extract from current message
        entities.update(self._extract_time(current_msg))
        entities.update(self._extract_email(current_msg))
        entities.update(self._extract_phone(current_msg))
        entities.update(self._extract_channel(current_msg))
        entities.update(self._extract_content_type(current_msg))
        
        # Check conversation history for missing entities
        history = state.get('conversation_history', [])
        for turn in reversed(history[-3:]):  # Last 3 turns
            content = turn.get('content', '').lower()
            
            # Fill in missing entities from history
            if 'email' not in entities:
                entities.update(self._extract_email(content))
            
            if 'callback_time' not in entities:
                entities.update(self._extract_time(content))
            
            if 'phone' not in entities:
                entities.update(self._extract_phone(content))
            
            if 'channel' not in entities:
                entities.update(self._extract_channel(content))
            
            if 'content_type' not in entities:
                entities.update(self._extract_content_type(content))
        
        return entities
    
    def _extract_time(self, text: str) -> dict:
        """Extract time/date from text"""
        patterns = [
            (r'(\d{1,2})\s*(am|pm)', 'callback_time'),
            (r'(\d{1,2}:\d{2})\s*(am|pm)?', 'callback_time'),
            (r'tomorrow', 'callback_time'),
            (r'today', 'callback_time'),
            (r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', 'callback_time'),
            (r'next\s+\w+', 'callback_time')
        ]
        
        for pattern, key in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return {key: match.group(0)}
        
        return {}
    
    def _extract_email(self, text: str) -> dict:
        """Extract email from text"""
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if match:
            return {'email': match.group(0)}
        return {}
    
    def _extract_phone(self, text: str) -> dict:
        """Extract phone from text"""
        match = re.search(r'\+?\d{10,}', text)
        if match:
            return {'phone': match.group(0)}
        return {}
    
    def _extract_channel(self, text: str) -> dict:
        """Extract channel preference from text"""
        if any(word in text for word in ['email', 'mail', 'e-mail']):
            return {'channel': 'email'}
        elif any(word in text for word in ['sms', 'text', 'message']):
            return {'channel': 'sms'}
        elif any(word in text for word in ['whatsapp', 'whats app', 'wa']):
            return {'channel': 'whatsapp'}
        return {}
    
    def _extract_content_type(self, text: str) -> dict:
        """Extract content type from text"""
        if any(word in text for word in ['price', 'pricing', 'cost']):
            return {'content_type': 'pricing'}
        elif any(word in text for word in ['product', 'features', 'specs']):
            return {'content_type': 'product'}
        elif any(word in text for word in ['catalog', 'catalogue', 'full details']):
            return {'content_type': 'catalog'}
        elif any(word in text for word in ['policy', 'refund', 'return']):
            return {'content_type': 'policy'}
        return {}
    
    # ========================================================================
    # POST-PROCESSING
    # ========================================================================
    
    def _post_process(self, intelligence: IntelligenceOutput, user_message: str, state: dict) -> IntelligenceOutput:
        """Post-process intelligence output"""
        
        # Extract entities from context if not present or incomplete
        context_entities = self._extract_entities_from_context(state)
        
        # Merge entities (LLM entities take precedence)
        merged_entities = {**context_entities, **intelligence.entities}
        intelligence.entities = merged_entities
        
        # Re-map actions based on updated entities
        if intelligence.intents:
            intelligence.next_actions = self._intents_to_actions(
                intelligence.intents,
                intelligence.entities
            )
        
        # Check if clarification needed
        intelligence = self._check_clarification_needed(intelligence)
        
        self.logger.debug(f"Post-process complete. Entities: {intelligence.entities}, Actions: {intelligence.next_actions}")
        
        return intelligence
    
    def _check_clarification_needed(self, intelligence: IntelligenceOutput) -> IntelligenceOutput:
        """Check if we need to ask for more information"""
        
        for intent in intelligence.intents:
            # Callback without time
            if intent == "callback_request" and not intelligence.entities.get("callback_time"):
                intelligence.needs_clarification = True
                intelligence.clarification_question = "What time would you like us to call you back?"
                intelligence.next_actions = []  # Don't schedule without time
            
            # Email send without email address
            elif intent == "send_details_email" and not intelligence.entities.get("email"):
                intelligence.needs_clarification = True
                intelligence.clarification_question = "What email address should I send this to?"
                intelligence.next_actions = [a for a in intelligence.next_actions if a != "send_email"]
        
        return intelligence
    
    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================
    
    def _update_state(
        self, 
        state: OptimizedWorkflowState, 
        user_message: str, 
        intelligence: IntelligenceOutput,
        execution_time: float
    ) -> OptimizedWorkflowState:
        """Update state with intelligence results"""
        
        # Store intelligence output
        state["intelligence_output"] = intelligence.dict()
        
        # Extract quick fields
        state = extract_quick_fields(state)
        
        # Update monitoring
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        state["node_execution_times"][self.name] = execution_time
        state["total_processing_time"] = state.get("total_processing_time", 0.0) + execution_time
        
        # Update conversation history
        state["conversation_history"].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        state["conversation_history"].append({
            "role": "assistant",
            "content": intelligence.response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return state
    
    # ========================================================================
    # ERROR HANDLING
    # ========================================================================
    
    def _fallback(self, user_message: str = "") -> IntelligenceOutput:
        """Return fallback response when parsing fails"""
        self.logger.warning("Using fallback response")
        
        return IntelligenceOutput(
            intent="general_inquiry",
            intents=["general_inquiry"],
            intent_confidence=0.5,
            entities={},
            sentiment="neutral",
            urgency="medium",
            response_text="I'm here to help! Could you please rephrase your question?",
            needs_clarification=True,
            clarification_question="Could you please provide more details?",
            next_actions=[],
            requires_human=False
        )
    
    def _handle_error(self, state: OptimizedWorkflowState, error_type: str, error_msg: str) -> OptimizedWorkflowState:
        """Handle errors gracefully"""
        self.logger.error(f"Error [{error_type}]: {error_msg}")
        
        if "errors" not in state:
            state["errors"] = []
        
        state["errors"].append({
            "type": error_type,
            "message": error_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "node": self.name
        })
        
        # Use fallback intelligence
        intelligence = self._fallback()
        state["intelligence_output"] = intelligence.dict()
        state = extract_quick_fields(state)
        
        return state