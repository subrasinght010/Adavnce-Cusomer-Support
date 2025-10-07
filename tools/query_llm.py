# tools/language_model.py

def query_llm(prompt: str) -> dict:
    """
    Replace this with your preferred LLM API or local model call.
    For example: OpenAI GPT, Mistral, LLaMA, etc.
    Should return a dict like {"preferred_channel": "...", "action": "..."}
    """

    # For now, a dummy rule-based fallback
    prompt_lower = prompt.lower()
    if "whatsapp" in prompt_lower:
        return {"preferred_channel": "whatsapp", "action": "reply"}
    elif "email" in prompt_lower:
        return {"preferred_channel": "email", "action": "reply"}
    elif "call" in prompt_lower:
        return {"preferred_channel": "call", "action": "schedule_call"}
    else:
        return {"preferred_channel": "email", "action": "reply"}
