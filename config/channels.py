"""
Channel Configuration - Settings for each communication channel
"""


class ChannelConfig:
    """Configuration for communication channels"""
    
    CHANNELS = {
        'email': {
            'name': 'Email',
            'check_interval': 30,  # seconds
            'response_target': 300,  # 5 minutes
            'retry_count': 3,
            'supports_media': True,
            'supports_threading': True,
            'max_message_length': None,  # unlimited
            'priority': 3  # 1=highest, 5=lowest
        },
        
        'sms': {
            'name': 'SMS',
            'check_interval': 0,  # webhook (instant)
            'response_target': 30,  # 30 seconds
            'retry_count': 2,
            'supports_media': False,
            'supports_threading': False,
            'max_message_length': 160,
            'priority': 1  # highest priority
        },
        
        'whatsapp': {
            'name': 'WhatsApp',
            'check_interval': 0,  # webhook (instant)
            'response_target': 30,  # 30 seconds
            'retry_count': 2,
            'supports_media': True,
            'supports_threading': False,
            'max_message_length': 4096,
            'priority': 2
        },
        
        'call': {
            'name': 'Voice Call',
            'check_interval': 0,  # real-time
            'response_target': 2,  # 2 seconds
            'retry_count': 1,
            'supports_media': False,
            'supports_threading': False,
            'max_message_length': None,
            'priority': 1  # highest priority
        }
    }
    
    @classmethod
    def get_channel_config(cls, channel: str) -> dict:
        """Get configuration for a specific channel"""
        return cls.CHANNELS.get(channel, cls.CHANNELS['email'])
    
    @classmethod
    def get_response_target(cls, channel: str) -> int:
        """Get response time target for channel"""
        return cls.CHANNELS.get(channel, {}).get('response_target', 60)
    
    @classmethod
    def supports_media(cls, channel: str) -> bool:
        """Check if channel supports media attachments"""
        return cls.CHANNELS.get(channel, {}).get('supports_media', False)
    
    @classmethod
    def get_max_length(cls, channel: str) -> int:
        """Get max message length for channel"""
        return cls.CHANNELS.get(channel, {}).get('max_message_length')
    
    @classmethod
    def truncate_message(cls, message: str, channel: str) -> str:
        """Truncate message if it exceeds channel limit"""
        max_length = cls.get_max_length(channel)
        
        if max_length and len(message) > max_length:
            return message[:max_length-3] + "..."
        
        return message