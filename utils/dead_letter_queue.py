"""
Dead Letter Queue - Store failed messages for manual review
"""

import json
from datetime import datetime
from typing import Dict, Optional
from database.crud import DBManager
from database.db import AsyncSessionLocal


class DeadLetterQueue:
    """Handle messages that failed processing"""
    
    async def add_to_dlq(
        self,
        message_type: str,
        message_data: Dict,
        error: str,
        retry_count: int = 0
    ):
        """
        Add failed message to dead letter queue
        
        Args:
            message_type: Type of message (sms, email, whatsapp)
            message_data: Original message data
            error: Error message
            retry_count: Number of retry attempts
        """
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                # Store in database
                dlq_entry = {
                    'type': message_type,
                    'data': message_data,
                    'error': error,
                    'retry_count': retry_count,
                    'failed_at': datetime.now().isoformat()
                }
                
                # Save to message_queue table with status='failed'
                lead_id = message_data.get('lead_id')
                
                if lead_id:
                    await db.enqueue_message(
                        lead_id=lead_id,
                        channel=message_type,
                        message_data=dlq_entry,
                        priority=10  # Low priority
                    )
                
                print(f"📝 Added to DLQ: {message_type} - {error[:100]}")
                
            except Exception as e:
                print(f"❌ Error adding to DLQ: {e}")
    
    async def get_dlq_messages(self, limit: int = 50):
        """Get messages from dead letter queue"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                # Get failed messages
                from sqlalchemy import select
                from database.models import MessageQueue
                
                result = await session.execute(
                    select(MessageQueue)
                    .filter_by(status='failed')
                    .order_by(MessageQueue.created_at.desc())
                    .limit(limit)
                )
                
                messages = result.scalars().all()
                return messages
                
            except Exception as e:
                print(f"❌ Error getting DLQ messages: {e}")
                return []
    
    async def retry_dlq_message(self, message_id: int):
        """Retry a message from dead letter queue"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                # Update status to pending for retry
                await db.update_queue_status(message_id, 'pending')
                print(f"♻️ Message {message_id} queued for retry")
                
            except Exception as e:
                print(f"❌ Error retrying DLQ message: {e}")


# Singleton instance
dlq = DeadLetterQueue()