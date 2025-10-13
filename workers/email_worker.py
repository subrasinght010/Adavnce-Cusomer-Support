# workers/email_worker.py
"""
Email Worker - Monitors incoming emails and triggers workflows
"""

from workers.base_worker import BaseWorker
from services.email_monitor import email_monitor


class EmailWorker(BaseWorker):
    """Email monitoring worker"""
    
    def __init__(self):
        super().__init__("email")
        self.email_monitor = email_monitor
    
    async def _run(self):
        """Main email monitoring loop"""
        await self.email_monitor.start_monitoring()
    
    async def stop(self):
        """Stop email monitoring"""
        self.email_monitor.stop_monitoring()
        await super().stop()
    
    def get_status(self) -> dict:
        """Enhanced status with email-specific info"""
        status = super().get_status()
        status.update({
            'check_interval': self.email_monitor.check_interval,
            'imap_server': self.email_monitor.imap_server,
            'username': self.email_monitor.username
        })
        return status


# Singleton instance
email_worker = EmailWorker()