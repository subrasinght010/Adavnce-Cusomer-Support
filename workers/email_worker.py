"""
Email Worker - Wrapper for EmailMonitor with standard worker interface
"""

import asyncio
from services.email_monitor import email_monitor


class EmailWorker:
    """Wrapper for EmailMonitor to match worker interface"""
    
    def __init__(self):
        self.email_monitor = email_monitor
        self.is_running = False
        self.task = None
    
    async def start(self):
        """Start email worker"""
        if self.is_running:
            print("⚠️ Email worker already running")
            return
        
        self.is_running = True
        print("🚀 Starting email worker...")
        
        try:
            # Start the email monitor
            self.task = asyncio.create_task(
                self.email_monitor.start_monitoring()
            )
            await self.task
        except asyncio.CancelledError:
            print("📧 Email worker cancelled")
        except Exception as e:
            print(f"❌ Email worker error: {e}")
            import traceback
            traceback.print_exc()
    
    async def stop(self):
        """Stop email worker"""
        if not self.is_running:
            return
        
        print("🛑 Stopping email worker...")
        self.is_running = False
        self.email_monitor.stop_monitoring()
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        print("✅ Email worker stopped")
    
    def get_status(self) -> dict:
        """Get worker status"""
        return {
            'running': self.is_running,
            'check_interval': self.email_monitor.check_interval,
            'imap_server': self.email_monitor.imap_server,
            'username': self.email_monitor.username
        }


# Singleton instance
email_worker = EmailWorker()