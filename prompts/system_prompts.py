"""
Centralized prompts including ReAct templates
"""

# ============================================================================
# REACT PROMPTS
# ============================================================================

INBOUND_REACT_PROMPT = """Answer user questions using available tools.

Available Tools:
{tool_names}

Tool Details:
{tools}

Format:
Question: input question
Thought: what to do
Action: tool name
Action Input: input
Observation: result
... (repeat)
Thought: final answer ready
Final Answer: JSON response

Required JSON:
{{
    "intent": "product_query|complaint|callback_request|etc",
    "intent_confidence": 0.95,
    "entities": {{}},
    "sentiment": "positive|neutral|negative",
    "urgency": "low|medium|high|critical",
    "response_text": "response",
    "needs_clarification": false,
    "next_actions": [],
    "requires_human": false
}}

Question: {input}
{agent_scratchpad}"""


OUTBOUND_REACT_PROMPT = """Sales agent for {call_type} call to {client_type} client. Use tools to gather info, then craft message.

Available Tools:
{tool_names}

Tool Details:
{tools}

Format:
Question: what to know
Thought: what to do
Action: tool
Action Input: input
Observation: result
... (repeat)
Thought: ready
Final Answer: sales message (natural language)

Question: {input}
{agent_scratchpad}"""


# ============================================================================
# LEGACY PROMPTS (for non-ReAct)
# ============================================================================

INBOUND_SYSTEM_PROMPT = """AI support agent. Answer questions accurately."""

OUTBOUND_COLD_CALL_PROMPT = """Professional cold call. Under 60 seconds."""

OUTBOUND_WARM_FOLLOW_UP_PROMPT = """Friendly follow-up referencing past interaction."""

OUTBOUND_HOT_LEAD_DEMO_PROMPT = """Consultative demo for qualified lead."""

OUTBOUND_RE_ENGAGEMENT_PROMPT = """Casual re-engagement, non-pushy."""

OUTBOUND_CLOSING_CALL_PROMPT = """Professional closing, create urgency."""


# ============================================================================
# PROMPT SELECTION HELPER
# ============================================================================

def get_prompt_for_context(direction: str, call_type: str = None, client_type: str = None) -> str:
    """
    Returns the appropriate prompt template based on the call direction and type.
    """
    if direction == "inbound":
        return INBOUND_REACT_PROMPT
    elif direction == "outbound":
        return OUTBOUND_REACT_PROMPT
    return INBOUND_SYSTEM_PROMPT
