"""
Metrics Collection - Prometheus metrics
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import Dict
import time


class Metrics:
    """Prometheus metrics collector"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Message counters
        self.messages_total = Counter(
            'messages_processed_total',
            'Total messages processed',
            ['channel', 'status'],
            registry=self.registry
        )
        
        # Response time histogram
        self.response_time = Histogram(
            'response_time_seconds',
            'Response time in seconds',
            ['channel', 'intent'],
            registry=self.registry
        )
        
        # Active conversations gauge
        self.active_conversations = Gauge(
            'active_conversations',
            'Number of active conversations',
            ['channel'],
            registry=self.registry
        )
        
        # Worker status
        self.worker_status = Gauge(
            'worker_status',
            'Worker running status (1=running, 0=stopped)',
            ['worker_name'],
            registry=self.registry
        )
        
        # Queue size
        self.queue_size = Gauge(
            'message_queue_size',
            'Number of messages in queue',
            registry=self.registry
        )
        
        # Error counter
        self.errors_total = Counter(
            'errors_total',
            'Total errors',
            ['error_type', 'channel'],
            registry=self.registry
        )
        
        # Lead metrics
        self.leads_total = Counter(
            'leads_total',
            'Total leads created',
            ['source'],
            registry=self.registry
        )
        
        self.lead_conversions = Counter(
            'lead_conversions_total',
            'Total lead conversions',
            ['source'],
            registry=self.registry
        )
    
    def record_message(self, channel: str, status: str):
        """Record a processed message"""
        self.messages_total.labels(channel=channel, status=status).inc()
    
    def record_response_time(self, channel: str, intent: str, duration: float):
        """Record response time"""
        self.response_time.labels(channel=channel, intent=intent).observe(duration)
    
    def set_active_conversations(self, channel: str, count: int):
        """Set active conversation count"""
        self.active_conversations.labels(channel=channel).set(count)
    
    def set_worker_status(self, worker_name: str, running: bool):
        """Set worker status"""
        self.worker_status.labels(worker_name=worker_name).set(1 if running else 0)
    
    def set_queue_size(self, size: int):
        """Set queue size"""
        self.queue_size.set(size)
    
    def record_error(self, error_type: str, channel: str):
        """Record an error"""
        self.errors_total.labels(error_type=error_type, channel=channel).inc()
    
    def record_lead(self, source: str):
        """Record new lead"""
        self.leads_total.labels(source=source).inc()
    
    def record_conversion(self, source: str):
        """Record lead conversion"""
        self.lead_conversions.labels(source=source).inc()
    
    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        """Get content type for metrics"""
        return CONTENT_TYPE_LATEST


# Singleton instance
metrics = Metrics()


class TimerContext:
    """Context manager for timing operations"""
    
    def __init__(self, metrics_obj: Metrics, channel: str, intent: str):
        self.metrics = metrics_obj
        self.channel = channel
        self.intent = intent
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.metrics.record_response_time(self.channel, self.intent, duration)


def timer(channel: str, intent: str = "unknown"):
    """
    Decorator/context manager for timing operations
    
    Usage as decorator:
        @timer(channel='sms', intent='query')
        async def process_message():
            ...
    
    Usage as context manager:
        with timer(channel='sms', intent='query'):
            # do work
            pass
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                metrics.record_response_time(channel, intent, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_response_time(channel, intent, duration)
                metrics.record_error(type(e).__name__, channel)
                raise
        return wrapper
    
    # Can be used as context manager too
    if callable(channel):
        # Called as @timer without arguments
        func = channel
        channel = "unknown"
        return decorator(func)
    
    return decorator