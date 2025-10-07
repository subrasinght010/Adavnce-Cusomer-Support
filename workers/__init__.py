"""
Workers Initialization - Manages all background workers
"""

import asyncio
from typing import Dict
from workers.email_worker import email_worker
from workers.followup_worker import followup_worker


class WorkerManager:
    def __init__(self):
        self.workers = {
            'email': email_worker,
            'followup': followup_worker
        }
        self.tasks = {}
    
    async def start_all_workers(self):
        """Start all background workers"""
        print("=" * 60)
        print("🚀 Starting all background workers...")
        print("=" * 60)
        
        for name, worker in self.workers.items():
            try:
                self.tasks[name] = asyncio.create_self.tasks[name] = asyncio.create_task(worker.start())
                print(f"✅ {name.capitalize()} worker started")
            except Exception as e:
                print(f"❌ Failed to start {name} worker: {e}")
        
        print("=" * 60)
        print("✅ All workers started successfully")
        print("=" * 60)
    
    async def stop_all_workers(self):
        """Stop all background workers"""
        print("\n" + "=" * 60)
        print("🛑 Stopping all background workers...")
        print("=" * 60)
        
        for name, worker in self.workers.items():
            try:
                await worker.stop()
                print(f"✅ {name.capitalize()} worker stopped")
            except Exception as e:
                print(f"❌ Error stopping {name} worker: {e}")
        
        # Cancel all tasks
        for name, task in self.tasks.items():
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.tasks.clear()
        
        print("=" * 60)
        print("✅ All workers stopped")
        print("=" * 60)
    
    def get_all_status(self) -> Dict:
        """Get status of all workers"""
        status = {}
        for name, worker in self.workers.items():
            try:
                status[name] = worker.get_status()
            except Exception as e:
                status[name] = {'error': str(e)}
        return status


# Singleton instance
worker_manager = WorkerManager()