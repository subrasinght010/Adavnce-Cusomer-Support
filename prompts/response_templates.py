"""
Response templates for controlled agent outputs
"""

RESPONSE_TEMPLATES = {
    "callback_scheduled": "Perfect! I've scheduled a callback for {time}. {name} from our team will call you at {phone}.",
    
    "callback_need_time": "I'd be happy to schedule a callback. What time works best for you?",
    
    "email_sent": "Done! I've sent the {content_type} to {email}. Check your inbox in 2-3 minutes.",
    
    "email_need_address": "I can send that to your email. What's your email address?",
    
    "pricing_query": "Our {product} starts at ${price}/month. Want me to send detailed pricing to your email?",
    
    "complaint_urgent": "I understand this is frustrating. Let me escalate this to a specialist who can help immediately.",
    
    "complaint_normal": "I'm sorry to hear that. Let me look into this and get back to you shortly.",
    
    "escalation": "Connecting you with a specialist now. They'll be able to assist you better.",
    
    "clarification": "To help you better, could you clarify: {question}?",
    
    "order_status": "Your order #{order_id} is {status}. Expected delivery: {date}.",
    
    "technical_issue": "Let me check our system status. Meanwhile, have you tried {troubleshooting_step}?",
    
    "out_of_scope": "That's outside my expertise. Let me connect you with the right team.",
}


def get_response(template_key: str, **kwargs) -> str:
    """Get templated response with variables"""
    template = RESPONSE_TEMPLATES.get(template_key, "How can I help you today?")
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# Add to system prompt
TEMPLATE_INSTRUCTION = """
=== RESPONSE CONTROL ===
For common scenarios, use these exact response patterns:

1. Callback scheduled: "Perfect! I've scheduled a callback for [time]. [Agent name] will call you."
2. Need time: "I'd be happy to schedule a callback. What time works best for you?"
3. Email sent: "Done! I've sent the [content] to [email]. Check your inbox in 2-3 minutes."
4. Need email: "I can send that to your email. What's your email address?"
5. Urgent complaint: "I understand this is frustrating. Escalating to a specialist now."
6. Clarification: "To help you better, could you clarify: [question]?"

Keep responses natural, under 50 words, and action-oriented.
"""