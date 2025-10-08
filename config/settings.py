# config/settings.py
"""
Unified Settings - Single source of truth for configuration
Uses environment-based config from config/environments.py
"""

import os
from config.environments import get_config
# Get configuration based on environment
from dotenv import load_dotenv
load_dotenv()
# Add any additional settings not in environments.py
class Settings:
    """Extended settings with additional attributes"""
    
    def __init__(self):
        # Load from environment config
        env_config = get_config()
        
        # Copy all attributes from environment config
        for key, value in vars(env_config).items():
            if not key.startswith('_'):
                setattr(self, key, value)
        
        # Additional settings
        self.RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
        self.RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
        
        # LLM Settings
        self.USE_OLLAMA = os.getenv('USE_OLLAMA', 'true').lower() == 'true'
        self.LLM_MODEL = os.getenv('LLM_MODEL', 'mistral')
        self.LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '512'))
        self.LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.7'))
        
        # RAG Settings
        self.RAG_ENABLED = os.getenv('RAG_ENABLED', 'true').lower() == 'true'
        self.RAG_TOP_K = int(os.getenv('RAG_TOP_K', '3'))
        self.RAG_RELEVANCE_THRESHOLD = float(os.getenv('RAG_RELEVANCE_THRESHOLD', '0.7'))
        
        # Company Info
        self.COMPANY_NAME = os.getenv('COMPANY_NAME', 'TechCorp')
        self.SUPPORT_NUMBER = os.getenv('SUPPORT_NUMBER', '+1-800-SUPPORT')
        self.FROM_EMAIL = os.getenv('FROM_EMAIL', 'support@techcorp.com')
        
        # Twilio
        self.TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
        self.TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
        self.TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
        self.TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')
        
        # SendGrid
        self.SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')

        self.ENABLE_TTS = os.getenv('ENABLE_TTS', 'false').lower() == 'true'

# Create singleton instance
settings = Settings()