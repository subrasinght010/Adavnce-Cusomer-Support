# workers/__init__.py
"""
Workers Initialization - Simplified with BaseWorker pattern
"""

import asyncio
from typing import Dict, List


class WorkerManager:
    """Manages all background workers"""
    
    def __init__(self):
        self.workers = {}
        self.tasks = {}
        self._initialized = False
    
    def _initialize_workers(self):
        """Lazy initialization to avoid circular imports"""
        if self._initialized:
            return
        
        # Import and register all workers
        worker_modules = [
            ('email', 'workers.email_worker', 'email_worker'),
            ('followup', 'workers.followup_worker', 'followup_worker'),
            ('execute_call', 'workers.execute_call_worker', 'execute_call_worker')
        ]
        
        for name, module_path, attr_name in worker_modules:
            try:
                module = __import__(module_path, fromlist=[attr_name])
                self.workers[name] = getattr(module, attr_name)
            except ImportError as e:
                print(f"⚠️  {name.capitalize()} worker not available: {e}")
        
        self._initialized = True
    
    async def start_all_workers(self):
        """Start all registered workers"""
        self._initialize_workers()
        
        if not self.workers:
            print("⚠️  No workers available to start")
            return
        
        print("=" * 60)
        print("🚀 Starting all background workers...")
        print("=" * 60)
        
        for name, worker in self.workers.items():
            try:
                self.tasks[name] = asyncio.create_task(
                    worker.start(),
                    name=f"worker_{name}"
                )
                print(f"✅ {name.capitalize()} worker started")
            except Exception as e:
                print(f"❌ Failed to start {name} worker: {e}")
        
        print("=" * 60)
        print(f"✅ {len(self.tasks)}/{len(self.workers)} workers started")
        print("=" * 60)
    
    async def stop_all_workers(self):
        """Stop all workers gracefully"""
        if not self.workers:
            return
        
        print("\n" + "=" * 60)
        print("🛑 Stopping all background workers...")
        print("=" * 60)
        
        # Stop each worker
        for name, worker in self.workers.items():
            try:
                await worker.stop()
                print(f"✅ {name.capitalize()} worker stopped")
            except Exception as e:
                print(f"❌ Error stopping {name} worker: {e}")
        
        # Cancel remaining tasks
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
        self._initialize_workers()
        
        status = {}
        for name, worker in self.workers.items():
            try:
                status[name] = worker.get_status()
            except Exception as e:
                status[name] = {'error': str(e), 'running': False}
        
        return status


# Singleton instance
worker_manager = WorkerManager()

__all__ = ['worker_manager', 'WorkerManager']