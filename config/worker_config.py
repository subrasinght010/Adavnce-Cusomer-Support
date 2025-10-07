"""
Worker Configuration - Settings for all background workers
"""

import os


class WorkerConfig:
    """Configuration for background workers"""
    
    # Email Worker
    EMAIL_CHECK_INTERVAL = int(os.getenv('EMAIL_CHECK_INTERVAL', '30'))  # seconds
    EMAIL_IMAP_SERVER = os.getenv('EMAIL_IMAP_SERVER', 'imap.gmail.com')
    EMAIL_IMAP_PORT = int(os.getenv('EMAIL_IMAP_PORT', '993'))
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    
    # Follow-up Worker
    FOLLOWUP_CHECK_INTERVAL = int(os.getenv('FOLLOWUP_CHECK_INTERVAL', '300'))  # 5 minutes
    FOLLOWUP_EMAIL_DELAY = int(os.getenv('FOLLOWUP_EMAIL_DELAY', '86400'))  # 24 hours
    FOLLOWUP_SMS_DELAY = int(os.getenv('FOLLOWUP_SMS_DELAY', '172800'))  # 48 hours
    FOLLOWUP_WHATSAPP_DELAY = int(os.getenv('FOLLOWUP_WHATSAPP_DELAY', '259200'))  # 72 hours
    FOLLOWUP_MAX_ATTEMPTS = int(os.getenv('FOLLOWUP_MAX_ATTEMPTS', '3'))
    
    # Callback Worker (future use)
    CALLBACK_CHECK_INTERVAL = int(os.getenv('CALLBACK_CHECK_INTERVAL', '60'))  # 1 minute
    
    # General Settings
    MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
    RETRY_DELAY = int(os.getenv('RETRY_DELAY', '60'))  # seconds
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        
        if not cls.EMAIL_USERNAME:
            errors.append("EMAIL_USERNAME not configured")
        
        if not cls.EMAIL_PASSWORD:
            errors.append("EMAIL_PASSWORD not configured")
        
        if errors:
            print("⚠️ Configuration warnings:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print configuration (for debugging)"""
        print("\n" + "=" * 60)
        print("WORKER CONFIGURATION")
        print("=" * 60)
        print(f"Email Check Interval: {cls.EMAIL_CHECK_INTERVAL}s")
        print(f"Follow-up Check Interval: {cls.FOLLOWUP_CHECK_INTERVAL}s")
        print(f"Follow-up Email Delay: {cls.FOLLOWUP_EMAIL_DELAY}s ({cls.FOLLOWUP_EMAIL_DELAY/3600}h)")
        print(f"Follow-up SMS Delay: {cls.FOLLOWUP_SMS_DELAY}s ({cls.FOLLOWUP_SMS_DELAY/3600}h)")
        print(f"Follow-up Max Attempts: {cls.FOLLOWUP_MAX_ATTEMPTS}")
        print(f"Max Retry Attempts: {cls.MAX_RETRY_ATTEMPTS}")
        print("=" * 60 + "\n")


# Validate on import
WorkerConfig.validate()