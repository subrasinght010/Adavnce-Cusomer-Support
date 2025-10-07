"""
Workers Initialization - Manages all background workers
"""

import asyncio
from typing import Dict


class WorkerManager:
    def __init__(self):
        self.workers = {}
        self.tasks = {}
        self._initialized = False
    
    def _initialize_workers(self):
        """Lazy initialization of workers to avoid circular imports"""
        if self._initialized:
            return
        
        try:
            from workers.email_worker import email_worker
            self.workers['email'] = email_worker
        except ImportError as e:
            print(f"⚠️  Email worker not available: {e}")
        
        try:
            from workers.followup_worker import followup_worker
            self.workers['followup'] = followup_worker
        except ImportError as e:
            print(f"⚠️  Followup worker not available: {e}")
        
        try:
            from workers.execute_call_worker import execute_call_worker
            self.workers['execute_call'] = execute_call_worker
        except ImportError as e:
            print(f"⚠️  Execute call worker not available: {e}")
        
        self._initialized = True
    
    async def start_all_workers(self):
        """Start all background workers"""
        self._initialize_workers()
        
        if not self.workers:
            print("⚠️  No workers available to start")
            return
        
        print("=" * 60)
        print("🚀 Starting all background workers...")
        print("=" * 60)
        
        for name, worker in self.workers.items():
            try:
                # Create task for worker
                self.tasks[name] = asyncio.create_task(
                    worker.start(),
                    name=f"worker_{name}"
                )
                print(f"✅ {name.capitalize()} worker started")
            except Exception as e:
                print(f"❌ Failed to start {name} worker: {e}")
                import traceback
                traceback.print_exc()
        
        print("=" * 60)
        print(f"✅ {len(self.tasks)}/{len(self.workers)} workers started")
        print("=" * 60)
    
    async def stop_all_workers(self):
        """Stop all background workers"""
        if not self.workers:
            return
        
        print("\n" + "=" * 60)
        print("🛑 Stopping all background workers...")
        print("=" * 60)
        
        # Stop each worker gracefully
        for name, worker in self.workers.items():
            try:
                if hasattr(worker, 'stop'):
                    await worker.stop()
                    print(f"✅ {name.capitalize()} worker stopped")
            except Exception as e:
                print(f"❌ Error stopping {name} worker: {e}")
        
        # Cancel all running tasks
        for name, task in self.tasks.items():
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    print(f"  Cancelled {name} worker task")
                except Exception as e:
                    print(f"  Error cancelling {name} task: {e}")
        
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
                if hasattr(worker, 'get_status'):
                    status[name] = worker.get_status()
                else:
                    # Check if task is running
                    task = self.tasks.get(name)
                    if task:
                        status[name] = {
                            'running': not task.done(),
                            'done': task.done(),
                            'cancelled': task.cancelled() if task.done() else False
                        }
                    else:
                        status[name] = {'running': False, 'status': 'not_started'}
            except Exception as e:
                status[name] = {'error': str(e), 'running': False}
        
        return status


# Singleton instance
worker_manager = WorkerManager()

# Export for easy import
__all__ = ['worker_manager', 'WorkerManager']