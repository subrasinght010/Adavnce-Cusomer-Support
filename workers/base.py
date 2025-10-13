# workers/base_worker.py
"""
Base Worker - Abstract base class for all background workers
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import datetime


class BaseWorker(ABC):
    """Abstract base class for background workers"""
    
    def __init__(self, name: str):
        self.name = name
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(f"worker.{name}")
        self.start_time: Optional[datetime] = None
    
    @abstractmethod
    async def _run(self):
        """
        Main worker loop - must be implemented by subclass
        Should contain the actual work logic
        """
        pass
    
    async def start(self):
        """Start the worker"""
        if self.is_running:
            self.logger.warning(f"{self.name} worker already running")
            return
        
        self.is_running = True
        self.start_time = datetime.utcnow()
        self.logger.info(f"🚀 Starting {self.name} worker...")
        
        try:
            self.task = asyncio.create_task(self._run())
            await self.task
        except asyncio.CancelledError:
            self.logger.info(f"🛑 {self.name} worker cancelled")
        except Exception as e:
            self.logger.error(f"❌ {self.name} worker error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
    
    async def stop(self):
        """Stop the worker gracefully"""
        if not self.is_running:
            return
        
        self.logger.info(f"🛑 Stopping {self.name} worker...")
        self.is_running = False
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        self.logger.info(f"✅ {self.name} worker stopped")
    
    def get_status(self) -> Dict:
        """Get worker status - can be overridden for more details"""
        uptime = None
        if self.start_time and self.is_running:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            'name': self.name,
            'running': self.is_running,
            'uptime_seconds': uptime,
            'start_time': self.start_time.isoformat() if self.start_time else None
        }