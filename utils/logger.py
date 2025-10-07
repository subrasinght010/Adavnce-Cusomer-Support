"""
Structured Logging - JSON formatted logs for better observability
"""

import logging
import json
import sys
from datetime import datetime
from typing import Dict, Any


class StructuredLogger:
    """JSON structured logger"""
    
    def __init__(self, name: str = "ai_agent"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Create console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)
    
    def info(self, message: str, **extra):
        """Log info message with structured data"""
        self.logger.info(message, extra=extra)
    
    def error(self, message: str, **extra):
        """Log error message with structured data"""
        self.logger.error(message, extra=extra)
    
    def warning(self, message: str, **extra):
        """Log warning message with structured data"""
        self.logger.warning(message, extra=extra)
    
    def debug(self, message: str, **extra):
        """Log debug message with structured data"""
        self.logger.debug(message, extra=extra)


class JsonFormatter(logging.Formatter):
    """Format logs as JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


# Create default logger instance
logger = StructuredLogger()