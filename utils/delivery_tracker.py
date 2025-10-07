"""
Delivery Tracker - Track message delivery status across channels
"""

import os
import asyncio
from typing import Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.db import AsyncSessionLocal
from twilio.rest import Client
from utils.logger import logger


class DeliveryTracker:
    """Track message delivery status"""
    
    def __init__(self):
        # Initialize Twilio client
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        
        if account_sid and auth_token:
            self.twilio_client = Client(account_sid, auth_token)
        else:
            self.twilio_client = None
            logger.warning("Twilio credentials not configured")
    
    async def track_sms_delivery(
        self,
        message_sid: str,
        conversation_id: int
    ):
        """
        Track SMS delivery status via Twilio
        
        Args:
            message_sid: Twilio message SID
            conversation_id: Database conversation ID
        """
        if not self.twilio_client:
            return
        
        try:
            # Query Twilio for message status
            message = self.twilio_client.messages(message_sid).fetch()
            
            status = message.status
            # Possible statuses: queued, sent, delivered, failed, undelivered
            
            # Map Twilio status to our status
            status_map = {
                'queued': 'pending',
                'sent': 'sent',
                'delivered': 'delivered',
                'failed': 'failed',
                'undelivered': 'failed'
            }
            
            our_status = status_map.get(status, 'pending')
            
            # Update database
            async with AsyncSessionLocal() as session:
                db = DBManager(session)
                await db.update_delivery_status(
                    conversation_id,
                    our_status
                )
            
            logger.info(
                "SMS delivery status updated",
                message_sid=message_sid,
                status=our_status
            )
            
        except Exception as e:
            logger.error(
                "Failed to track SMS delivery",
                message_sid=message_sid,
                error=str(e)
            )
    
    async def track_whatsapp_delivery(
        self,
        message_sid: str,
        conversation_id: int
    ):
        """
        Track WhatsApp delivery status via Twilio
        """
        # Same as SMS tracking
        await self.track_sms_delivery(message_sid, conversation_id)
    
    async def track_email_delivery(
        self,
        message_id: str,
        conversation_id: int
    ):
        """
        Track email delivery status via SendGrid
        
        Note: Requires SendGrid webhooks to be configured
        """
        # SendGrid uses webhooks for delivery tracking
        # This would be called from a webhook endpoint
        logger.info(
            "Email tracking requires webhook configuration",
            message_id=message_id
        )
    
    async def update_delivery_status_from_webhook(
        self,
        message_id: str,
        status: str,
        event_data: Dict
    ):
        """
        Update delivery status from webhook event
        
        Args:
            message_id: External message ID
            status: Delivery status
            event_data: Event data from webhook
        """
        try:
            async with AsyncSessionLocal() as session:
                db = DBManager(session)
                
                # Find conversation by message_id
                conv = await db.get_conversation_by_message_id(message_id)
                
                if not conv:
                    logger.warning(
                        "Conversation not found for delivery update",
                        message_id=message_id
                    )
                    return
                
                # Update status
                await db.update_delivery_status(conv.id, status)
                
                logger.info(
                    "Delivery status updated from webhook",
                    message_id=message_id,
                    status=status
                )
                
        except Exception as e:
            logger.error(
                "Failed to update delivery status",
                message_id=message_id,
                error=str(e)
            )
    
    async def get_delivery_report(
        self,
        lead_id: int,
        hours: int = 24
    ) -> Dict:
        """
        Get delivery report for a lead
        
        Args:
            lead_id: Lead ID
            hours: Hours to look back
        
        Returns:
            Delivery statistics
        """
        try:
            async with AsyncSessionLocal() as session:
                db = DBManager(session)
                
                # Get recent conversations
                convs = await db.get_recent_conversations(
                    lead_id,
                    hours=hours,
                    limit=100
                )
                
                # Count by status
                stats = {
                    'total': len(convs),
                    'pending': 0,
                    'sent': 0,
                    'delivered': 0,
                    'failed': 0,
                    'by_channel': {}
                }
                
                for conv in convs:
                    # Count by status
                    status = conv.delivery_status or 'pending'
                    stats[status] = stats.get(status, 0) + 1
                    
                    # Count by channel
                    channel = conv.channel
                    if channel not in stats['by_channel']:
                        stats['by_channel'][channel] = {
                            'total': 0,
                            'delivered': 0,
                            'failed': 0
                        }
                    
                    stats['by_channel'][channel]['total'] += 1
                    if status == 'delivered':
                        stats['by_channel'][channel]['delivered'] += 1
                    elif status == 'failed':
                        stats['by_channel'][channel]['failed'] += 1
                
                # Calculate delivery rate
                if stats['total'] > 0:
                    stats['delivery_rate'] = (
                        stats['delivered'] / stats['total']
                    ) * 100
                else:
                    stats['delivery_rate'] = 0
                
                return stats
                
        except Exception as e:
            logger.error(
                "Failed to get delivery report",
                lead_id=lead_id,
                error=str(e)
            )
            return {}
    
    async def check_pending_deliveries(self):
        """
        Background task to check pending delivery statuses
        Should be run periodically
        """
        try:
            async with AsyncSessionLocal() as session:
                db = DBManager(session)
                
                # Get conversations with pending delivery status
                from sqlalchemy import select, and_
                from database.models import Conversation
                from datetime import timedelta
                
                cutoff = datetime.now() - timedelta(hours=1)
                
                result = await session.execute(
                    select(Conversation).filter(
                        and_(
                            Conversation.delivery_status == 'pending',
                            Conversation.timestamp > cutoff,
                            Conversation.message_id.isnot(None)
                        )
                    ).limit(50)
                )
                
                pending_convs = result.scalars().all()
                
                logger.info(
                    "Checking pending deliveries",
                    count=len(pending_convs)
                )
                
                # Check each one
                for conv in pending_convs:
                    if conv.channel in ['sms', 'whatsapp']:
                        await self.track_sms_delivery(
                            conv.message_id,
                            conv.id
                        )
                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(
                "Failed to check pending deliveries",
                error=str(e)
            )


# Singleton instance
delivery_tracker = DeliveryTracker()