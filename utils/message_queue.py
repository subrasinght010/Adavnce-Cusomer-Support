"""
Message Queue System - Handle high traffic with queuing
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque
from database.crud import DBManager
from database.db import AsyncSessionLocal
from utils.logger import logger


class MessageQueue:
    """In-memory message queue with database persistence"""
    
    def __init__(self):
        self.queue = deque()
        self.processing = False
        self.max_queue_size = 1000
        self.batch_size = 10
        self.processing_delay = 0.1  # seconds between batches
    
    async def enqueue(
        self,
        message_type: str,
        message_data: Dict,
        priority: int = 5,
        lead_id: Optional[int] = None
    ) -> bool:
        """
        Add message to queue
        
        Args:
            message_type: Type (sms, email, whatsapp)
            message_data: Message data
            priority: Priority (1=highest, 10=lowest)
            lead_id: Optional lead ID
        
        Returns:
            True if enqueued successfully
        """
        try:
            # Check queue size
            if len(self.queue) >= self.max_queue_size:
                logger.warning(
                    "Queue full, rejecting message",
                    queue_size=len(self.queue),
                    max_size=self.max_queue_size
                )
                return False
            
            # Create queue item
            queue_item = {
                'id': f"{message_type}_{datetime.now().timestamp()}",
                'type': message_type,
                'data': message_data,
                'priority': priority,
                'lead_id': lead_id,
                'enqueued_at': datetime.now(),
                'retry_count': 0
            }
            
            # Add to queue (sorted by priority)
            self.queue.append(queue_item)
            
            # Also persist to database
            if lead_id:
                await self._persist_to_db(queue_item)
            
            logger.info(
                "Message enqueued",
                message_type=message_type,
                queue_size=len(self.queue),
                priority=priority
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to enqueue message",
                error=str(e),
                message_type=message_type
            )
            return False
    
    async def _persist_to_db(self, queue_item: Dict):
        """Persist queue item to database"""
        try:
            async with AsyncSessionLocal() as session:
                db = DBManager(session)
                
                await db.enqueue_message(
                    lead_id=queue_item['lead_id'],
                    channel=queue_item['type'],
                    message_data=queue_item['data'],
                    priority=queue_item['priority']
                )
        except Exception as e:
            logger.error("Failed to persist queue item", error=str(e))
    
    async def dequeue(self) -> Optional[Dict]:
        """Get next message from queue"""
        if not self.queue:
            return None
        
        # Sort by priority before dequeuing
        self.queue = deque(
            sorted(self.queue, key=lambda x: x['priority'])
        )
        
        return self.queue.popleft()
    
    async def process_queue(self):
        """Process messages from queue"""
        if self.processing:
            logger.warning("Queue processing already running")
            return
        
        self.processing = True
        logger.info("Queue processing started")
        
        try:
            while self.processing:
                # Check if queue is empty
                if not self.queue:
                    await asyncio.sleep(1)
                    continue
                
                # Process batch
                batch = []
                for _ in range(min(self.batch_size, len(self.queue))):
                    item = await self.dequeue()
                    if item:
                        batch.append(item)
                
                if batch:
                    await self._process_batch(batch)
                
                # Small delay between batches
                await asyncio.sleep(self.processing_delay)
                
        except Exception as e:
            logger.error("Queue processing error", error=str(e))
        finally:
            self.processing = False
            logger.info("Queue processing stopped")
    
    async def _process_batch(self, batch: List[Dict]):
        """Process batch of messages"""
        logger.info(
            "Processing batch",
            batch_size=len(batch)
        )
        
        # Process messages in parallel
        tasks = [self._process_message(item) for item in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        success_count = sum(1 for r in results if r is True)
        logger.info(
            "Batch processed",
            total=len(batch),
            success=success_count,
            failed=len(batch) - success_count
        )
    
    async def _process_message(self, item: Dict) -> bool:
        """Process single message"""
        try:
            message_type = item['type']
            message_data = item['data']
            
            # Route to appropriate handler
            if message_type == 'sms':
                from services.sms_handler import sms_handler
                result = await sms_handler.handle_incoming_sms(message_data)
            elif message_type == 'whatsapp':
                from services.whatsapp_handler import whatsapp_handler
                result = await whatsapp_handler.handle_incoming_whatsapp(message_data)
            elif message_type == 'email':
                # Handle email processing
                pass
            
            logger.info(
                "Message processed",
                message_id=item['id'],
                message_type=message_type
            )
            return True
            
        except Exception as e:
            logger.error(
                "Message processing failed",
                message_id=item['id'],
                error=str(e)
            )
            
            # Retry logic
            if item['retry_count'] < 3:
                item['retry_count'] += 1
                self.queue.append(item)
                logger.info(
                    "Message requeued for retry",
                    message_id=item['id'],
                    retry_count=item['retry_count']
                )
            else:
                # Move to DLQ after max retries
                from utils.dead_letter_queue import dlq
                await dlq.add_to_dlq(
                    message_type=item['type'],
                    message_data=item['data'],
                    error=str(e),
                    retry_count=item['retry_count']
                )
            
            return False
    
    def get_queue_size(self) -> int:
        """Get current queue size"""
        return len(self.queue)
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        if not self.queue:
            return {
                'size': 0,
                'oldest_message_age_seconds': 0,
                'by_priority': {}
            }
        
        # Calculate stats
        now = datetime.now()
        oldest = min(item['enqueued_at'] for item in self.queue)
        age_seconds = (now - oldest).total_seconds()
        
        # Count by priority
        by_priority = {}
        for item in self.queue:
            priority = item['priority']
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        return {
            'size': len(self.queue),
            'oldest_message_age_seconds': age_seconds,
            'by_priority': by_priority,
            'processing': self.processing
        }
    
    def stop_processing(self):
        """Stop queue processing"""
        self.processing = False


# Singleton instance
message_queue = MessageQueue()