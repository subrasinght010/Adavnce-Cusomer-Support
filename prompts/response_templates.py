# prompts/response_templates.py
"""
Response templates for common scenarios
Ensures consistent messaging
"""

RESPONSE_TEMPLATES = {
    "greeting": "Hello! How can I assist you today?",
    
    "email_need_address": "I'd be happy to email that to you! What email address should I use?",
    
    "callback_need_time": "I'll schedule a callback for you. What time works best?",
    
    "sms_confirm": "I'll send that to you via SMS right away.",
    
    "whatsapp_confirm": "I'll send that to you on WhatsApp.",
    
    "escalation_confirm": "I understand your concern. I'm escalating this to a senior agent who will contact you shortly.",
    
    "clarification": "Could you provide more details about {question}?",
    
    "multi_action_confirm": "Got it! I'll {actions}. Is there anything else I can help with?",
    
    "error": "I apologize, but I'm having trouble processing that request. Let me connect you with a human agent.",
}


def get_response(template_key: str, **kwargs) -> str:
    """Get response template with variable substitution"""
    template = RESPONSE_TEMPLATES.get(template_key, RESPONSE_TEMPLATES["error"])
    
    try:
        return template.format(**kwargs)
    except KeyError:
        return template