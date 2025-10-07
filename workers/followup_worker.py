"""
Follow-up Worker - Background worker for automated follow-ups
"""

import asyncio
from services.follow_up_manager import follow_up_manager


class FollowUpWorker:
    def __init__(self):
        self.is_running = False
        self.task = None
    
    async def start(self):
        """Start follow-up worker"""
        if self.is_running:
            print("⚠️ Follow-up worker already running")
            return
        
        self.is_running = True
        print("🚀 Starting follow-up worker...")
        
        try:
            self.task = asyncio.create_task(follow_up_manager.start_monitoring())
            await self.task
        except asyncio.CancelledError:
            print("🔔 Follow-up worker cancelled")
        except Exception as e:
            print(f"❌ Follow-up worker error: {e}")
            import traceback
            traceback.print_exc()
    
    async def stop(self):
        """Stop follow-up worker"""
        if not self.is_running:
            return
        
        print("🛑 Stopping follow-up worker...")
        self.is_running = False
        follow_up_manager.stop_monitoring()
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        print("✅ Follow-up worker stopped")
    
    def get_status(self) -> dict:
        """Get worker status"""
        return {
            'running': self.is_running,
            'check_interval': follow_up_manager.check_interval,
            'max_attempts': follow_up_manager.max_attempts
        }


# Singleton instance
followup_worker = FollowUpWorker()