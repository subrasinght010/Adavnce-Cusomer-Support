from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta
from typing import List, Optional
from .models import Lead, Conversation, User, FollowUp, MessageQueue

class DBManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    # =============================
    # LEAD CRUD - UPDATED
    # =============================
    
    async def add_lead(self, name: str, email: str, phone: str, client_type=None):
        lead = Lead(
            name=name, 
            email=email, 
            phone=phone, 
            client_type=client_type,
            message_count=0,
            followup_count=0
        )
        self.session.add(lead)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def get_lead_by_id(self, lead_id: int):
        result = await self.session.execute(select(Lead).filter_by(id=lead_id))
        return result.scalar_one_or_none()

    async def get_lead_by_email(self, email: str):
        result = await self.session.execute(select(Lead).filter_by(email=email))
        return result.scalar_one_or_none()
    
    async def get_lead_by_phone(self, phone: str):
        """NEW: Get lead by phone number"""
        result = await self.session.execute(select(Lead).filter_by(phone=phone))
        return result.scalar_one_or_none()
    
    async def get_lead_by_whatsapp(self, whatsapp: str):
        """NEW: Get lead by WhatsApp number (same as phone)"""
        # Clean WhatsApp prefix if present
        phone = whatsapp.replace('whatsapp:', '').strip()
        return await self.get_lead_by_phone(phone)
    
    async def get_or_create_lead(self, email: str = None, phone: str = None, name: str = "Unknown"):
        """NEW: Get existing lead or create new one"""
        lead = None
        
        if email:
            lead = await self.get_lead_by_email(email)
        
        if not lead and phone:
            lead = await self.get_lead_by_phone(phone)
        
        if not lead:
            # Create new lead
            lead = Lead(
                name=name,
                email=email or f"unknown_{phone}@temp.com",
                phone=phone or "+00000000000",
                client_type="new",
                message_count=0,
                followup_count=0
            )
            self.session.add(lead)
            await self.session.commit()
            await self.session.refresh(lead)
        
        return lead
    
    async def update_lead_last_message(self, lead_id: int):
        """NEW: Update last message timestamp"""
        lead = await self.get_lead_by_id(lead_id)
        if lead:
            lead.last_message_at = datetime.now()
            lead.message_count += 1
            await self.session.commit()
    
    async def get_user_by_username(self, username: str):
        result = await self.session.execute(select(User).filter_by(username=username))
        return result.scalar_one_or_none()

    # =============================
    # CONVERSATION CRUD - UPDATED
    # =============================
    
    async def add_conversation(
        self, 
        lead_id: int, 
        message: str, 
        channel: str,
        sender: str = "user",
        parent_message_id: int = None,
        message_id: str = None,
        intent_detected: str = None,
        metadata: dict = None
    ):
        """NEW: Enhanced conversation creation with threading support"""
        conv = Conversation(
            lead_id=lead_id,
            message=message,
            channel=channel,
            sender=sender,
            parent_message_id=parent_message_id,
            message_id=message_id,
            intent_detected=intent_detected,
            metadata=metadata,
            delivery_status="sent" if sender == "ai" else "received"
        )
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        
        # Update lead's last message time
        await self.update_lead_last_message(lead_id)
        
        return conv

    async def get_conversations_by_lead(self, lead_id: int, limit: int = 50):
        """Get conversations ordered by timestamp"""
        result = await self.session.execute(
            select(Conversation)
            .filter_by(lead_id=lead_id)
            .order_by(desc(Conversation.timestamp))
            .limit(limit)
        )
        conversations = result.scalars().all()
        return list(reversed(conversations))  # Return in chronological order
    
    async def get_conversation_by_message_id(self, message_id: str):
        """NEW: Find conversation by external message ID"""
        result = await self.session.execute(
            select(Conversation).filter_by(message_id=message_id)
        )
        return result.scalar_one_or_none()
    
    async def get_conversation_thread(self, lead_id: int, channel: str = None):
        """NEW: Get conversation thread for a lead, optionally filtered by channel"""
        query = select(Conversation).filter_by(lead_id=lead_id)
        
        if channel:
            query = query.filter_by(channel=channel)
        
        query = query.order_by(Conversation.timestamp)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_recent_conversations(self, lead_id: int, hours: int = 24, limit: int = 10):
        """NEW: Get recent conversations within specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        result = await self.session.execute(
            select(Conversation)
            .filter(
                and_(
                    Conversation.lead_id == lead_id,
                    Conversation.timestamp >= cutoff_time
                )
            )
            .order_by(desc(Conversation.timestamp))
            .limit(limit)
        )
        conversations = result.scalars().all()
        return list(reversed(conversations))
    
    async def find_parent_message(self, message_id: str):
        """NEW: Find parent message in email thread"""
        conv = await self.get_conversation_by_message_id(message_id)
        if conv and conv.parent_message_id:
            result = await self.session.execute(
                select(Conversation).filter_by(id=conv.parent_message_id)
            )
            return result.scalar_one_or_none()
        return None
    
    async def update_delivery_status(self, conversation_id: int, status: str, read_at: datetime = None):
        """NEW: Update message delivery status"""
        conv = await self.session.execute(
            select(Conversation).filter_by(id=conversation_id)
        )
        conversation = conv.scalar_one_or_none()
        
        if conversation:
            conversation.delivery_status = status
            if read_at:
                conversation.read_at = read_at
            await self.session.commit()
            return conversation
        return None

    # =============================
    # FOLLOW-UP CRUD - NEW
    # =============================
    
    async def create_followup(
        self,
        lead_id: int,
        scheduled_time: datetime,
        followup_type: str,
        channel: str,
        message_template: str = None
    ):
        """NEW: Create a follow-up task"""
        followup = FollowUp(
            lead_id=lead_id,
            scheduled_time=scheduled_time,
            followup_type=followup_type,
            channel=channel,
            message_template=message_template,
            status="scheduled"
        )
        self.session.add(followup)
        await self.session.commit()
        await self.session.refresh(followup)
        return followup
    
    async def get_pending_followups(self):
        """NEW: Get all follow-ups that are due"""
        now = datetime.now()
        result = await self.session.execute(
            select(FollowUp)
            .filter(
                and_(
                    FollowUp.status == "scheduled",
                    FollowUp.scheduled_time <= now
                )
            )
            .order_by(FollowUp.scheduled_time)
        )
        return result.scalars().all()
    
    async def update_followup_status(self, followup_id: int, status: str):
        """NEW: Update follow-up status"""
        result = await self.session.execute(
            select(FollowUp).filter_by(id=followup_id)
        )
        followup = result.scalar_one_or_none()
        
        if followup:
            followup.status = status
            if status == "sent":
                followup.sent_at = datetime.now()
            await self.session.commit()
            return followup
        return None
    
    async def get_leads_needing_followup(self, hours_since_contact: int = 24):
        """NEW: Get leads that haven't been contacted recently"""
        cutoff_time = datetime.now() - timedelta(hours=hours_since_contact)
        result = await self.session.execute(
            select(Lead)
            .filter(
                and_(
                    Lead.last_contacted_at < cutoff_time,
                    Lead.lead_status.in_(["contacted", "qualified"]),
                    Lead.response_received == False
                )
            )
        )
        return result.scalars().all()

    # =============================
    # MESSAGE QUEUE CRUD - NEW
    # =============================
    
    async def enqueue_message(
        self,
        lead_id: int,
        channel: str,
        message_data: dict,
        priority: int = 5
    ):
        """NEW: Add message to processing queue"""
        queue_item = MessageQueue(
            lead_id=lead_id,
            channel=channel,
            message_data=message_data,
            priority=priority,
            status="pending"
        )
        self.session.add(queue_item)
        await self.session.commit()
        await self.session.refresh(queue_item)
        return queue_item
    
    async def get_pending_messages(self, limit: int = 10):
        """NEW: Get pending messages from queue"""
        result = await self.session.execute(
            select(MessageQueue)
            .filter_by(status="pending")
            .order_by(MessageQueue.priority, MessageQueue.created_at)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def update_queue_status(
        self,
        queue_id: int,
        status: str,
        error_message: str = None
    ):
        """NEW: Update queue item status"""
        result = await self.session.execute(
            select(MessageQueue).filter_by(id=queue_id)
        )
        queue_item = result.scalar_one_or_none()
        
        if queue_item:
            queue_item.status = status
            queue_item.processed_at = datetime.now()
            if error_message:
                queue_item.error_message = error_message
                queue_item.retry_count += 1
            await self.session.commit()
            return queue_item
        return None