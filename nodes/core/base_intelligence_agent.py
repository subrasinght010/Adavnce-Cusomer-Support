"""Base Intelligence Agent - Shared logic for all agents"""
import json
from datetime import datetime
from abc import abstractmethod
from langchain_core.tools import Tool

from nodes.core.base_node import BaseNode
from nodes.core.intelligence_models import IntelligenceOutput
from state.workflow_state import OptimizedWorkflowState, extract_quick_fields


class BaseIntelligenceAgent(BaseNode):
    """Base class for intelligence agents with ReAct loop"""
    
    def __init__(self, name: str, llm):
        super().__init__(name)
        self.llm = llm
        self.tools = self._create_tools()
    
    @abstractmethod
    def _create_tools(self) -> list:
        """Override to define agent-specific tools"""
        pass
    
    @abstractmethod
    def _get_system_prompt(self, **kwargs) -> str:
        """Override to define agent-specific prompt"""
        pass
    
    async def execute(self, state: OptimizedWorkflowState) -> OptimizedWorkflowState:
        """Main execution with ReAct loop"""
        self._pending_sends = []

        user_message = state.get('current_message')
        self.logger.info(f"Executing agent for message: {user_message[:50]}...")
        
        # Build context
        context = self._build_context(state)
        self.logger.debug("Context built successfully")
        
        # ReAct loop
        try:
            intelligence = await self._react_loop(context, max_iterations=3)
            intelligence = self._post_process(intelligence, user_message, state)
            self.logger.info(f"Generated response - Intent: {intelligence.intent}, Confidence: {intelligence.intent_confidence}")
        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            intelligence = self._fallback()
        
        # Update state
        if hasattr(self, '_pending_sends') and self._pending_sends:
            if "pending_sends" not in state:
                state["pending_sends"] = []
            state["pending_sends"].extend(self._pending_sends)
        return self._update_state(state, user_message, intelligence)
    
    def _build_context(self, state: dict) -> str:
        """Build prompt context"""
        history = self._format_history(state.get('conversation_history', []))
        prompt_kwargs = self._extract_prompt_vars(state)
        return self._get_system_prompt(
            conversation_history=history,
            tools_description=self._format_tools(),
            **prompt_kwargs
        )
    
    async def _react_loop(self, context: str, max_iterations: int) -> IntelligenceOutput:
        """ReAct reasoning loop"""
        self.logger.info(f"Starting ReAct loop (max {max_iterations} iterations)")
        scratchpad = ""
        
        for iteration in range(max_iterations):
            self.logger.debug(f"Iteration {iteration + 1}/{max_iterations}")
            
            response = await self._llm_call(context + scratchpad)
            self.logger.debug(f"LLM response: {response[:200]}...")
            
            # Check for answer
            if "Final Answer:" in response or ("{" in response and "intent" in response):
                self.logger.info("Found final answer")
                answer = response.split("Final Answer:")[1] if "Final Answer:" in response else response
                return self._parse(answer)
            
            # Execute tool
            if "Action:" in response and "Action Input:" in response:
                action = self._extract_action(response)
                if action:
                    tool_name, tool_input = action
                    self.logger.info(f"Executing tool: {tool_name} with input: {tool_input[:50]}...")
                    observation = self._execute_tool(tool_name, tool_input)
                    self.logger.info(f"Tool result: {observation[:100]}...")
                    scratchpad += f"\nAction: {tool_name}\nAction Input: {tool_input}\nObservation: {observation}\n"
                    continue
            
            self.logger.info("No tool action found, parsing as final answer")
            return self._parse(response)
        
        self.logger.warning("Max iterations reached, using fallback")
        return self._fallback()
    
    def _post_process(self, intelligence: IntelligenceOutput, user_message: str, state: dict) -> IntelligenceOutput:
        """Post-processing hooks"""
        self.logger.debug("Running post-processing validation")
        intelligence = self._validate_entities(intelligence, user_message)
        intelligence = self._apply_response_template(intelligence, state)
        return intelligence
    
    def _validate_entities(self, intelligence: IntelligenceOutput, user_message: str) -> IntelligenceOutput:
        """Override for agent-specific validation"""
        return intelligence
    
    def _apply_response_template(self, intelligence: IntelligenceOutput, state: dict) -> IntelligenceOutput:
        """Override for agent-specific templates"""
        return intelligence
    
    def _update_state(self, state: dict, user_message: str, intelligence: IntelligenceOutput) -> dict:
        """Update conversation state"""
        self.logger.debug("Updating conversation state")
        state["conversation_history"].append({"role": "user", "content": user_message, "timestamp": datetime.utcnow().isoformat()})
        state["intelligence_output"] = intelligence.dict()
        state = extract_quick_fields(state)
        state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1
        state["conversation_history"].append({"role": "assistant", "content": intelligence.response_text, "timestamp": datetime.utcnow().isoformat()})
        self.logger.info(f"State updated - Conversation history: {len(state['conversation_history'])} messages")
        return state
    
    # Utility methods
    def _format_history(self, history: list) -> str:
        return "\n".join([f"{m['role']}: {m['content']}" for m in history[-5:]]) if history else "No previous conversation"
    
    def _format_tools(self) -> str:
        return "\n".join([f"- {t.name}: {t.description}" for t in self.tools])
    
    def _extract_prompt_vars(self, state: dict) -> dict:
        """Override to extract state vars for prompt"""
        return {}
    
    async def _llm_call(self, prompt: str) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.llm._call, prompt)
    
    def _extract_action(self, text: str) -> tuple:
        try:
            action = [l for l in text.split('\n') if l.strip().startswith('Action:')][0].split('Action:')[1].strip()
            action_input = [l for l in text.split('\n') if l.strip().startswith('Action Input:')][0].split('Action Input:')[1].strip()
            return (action, action_input)
        except:
            return None
    
    def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        for tool in self.tools:
            if tool.name == tool_name:
                try:
                    result = tool.func(tool_input)
                    return result
                except Exception as e:
                    self.logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
                    return f"Tool error: {e}"
        self.logger.warning(f"Tool not found: {tool_name}")
        return f"Tool '{tool_name}' not found"
    
    def _parse(self, text: str) -> IntelligenceOutput:
        try:
            cleaned = text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            if start >= 0 and end > start:
                cleaned = cleaned[start:end]
            
            cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
            data = json.loads(cleaned)
            
            if 'intent' not in data:
                data['intent'] = 'general_inquiry'
            if 'response_text' not in data:
                data['response_text'] = data.get('message', 'How can I help?')
            
            if 'next_actions' in data:
                actions = data['next_actions']
                if isinstance(actions, list):
                    data['next_actions'] = [
                        a if isinstance(a, str) else str(a.get('action', a.get('Action', '')))
                        for a in actions
                    ]
            
            self.logger.debug(f"Parsed intent: {data.get('intent')}")
            return IntelligenceOutput(**data)
        except Exception as e:
            self.logger.warning(f"Parse failed: {e}, using fallback")
            return self._fallback()
    
    def _fallback(self) -> IntelligenceOutput:
        return IntelligenceOutput(
            intent="general_inquiry",
            intent_confidence=0.5,
            sentiment="neutral",
            urgency="medium",
            response_text="I'm here to help. Could you please rephrase?"
        )