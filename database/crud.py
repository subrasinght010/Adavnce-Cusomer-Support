from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import logging

from .models import (
    Lead, Conversation, User, FollowUp, MessageQueue,
    Organization, Client, SupportTicket, EmailMessage, 
    Attachment, Campaign
)

logger = logging.getLogger(__name__)


class DBManager:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ============================================================================
    # QUERY HELPERS
    # ============================================================================
    
    def _filter_deleted(self, query):
        """Filter soft-deleted records"""
        return query.filter_by(is_deleted=False)
    
    # ============================================================================
    # LEAD CRUD
    # ============================================================================
    
    async def add_lead(
        self,
        name: str,
        email: str,
        phone: str,
        organization_id: int = None,
        whatsapp_number: str = None,
        source: str = None,
        utm_json: dict = None
    ):
        """Create new lead"""
        try:
            lead = Lead(
                name=name,
                email=email,
                phone=phone,
                organization_id=organization_id,
                whatsapp_number=whatsapp_number,
                source=source,
                utm_json=utm_json,
                message_count=0,
                engagement_score=0
            )
            self.session.add(lead)
            await self.session.commit()
            await self.session.refresh(lead)
            
            logger.info(f"Lead created: {lead.id} - {name} ({email})")
            return lead
        except Exception as e:
            logger.error(f"Failed to create lead: {e}", exc_info=True)
            await self.session.rollback()
            raise

    async def get_lead_by_id(self, lead_id: int, include_deleted: bool = False):
        """Get lead by ID"""
        try:
            query = select(Lead).filter_by(id=lead_id)
            if not include_deleted:
                query = self._filter_deleted(query)
            
            result = await self.session.execute(query)
            lead = result.scalar_one_or_none()
            
            if lead:
                logger.debug(f"Lead retrieved: {lead_id}")
            else:
                logger.warning(f"Lead not found: {lead_id}")
            
            return lead
        except Exception as e:
            logger.error(f"Failed to get lead {lead_id}: {e}")
            return None

    async def get_lead_by_email(self, email: str):
        """Get lead by email"""
        try:
            query = select(Lead).filter_by(email=email)
            query = self._filter_deleted(query)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get lead by email {email}: {e}")
            return None
    
    async def get_lead_by_phone(self, phone: str):
        """Get lead by phone"""
        try:
            query = select(Lead).filter_by(phone=phone)
            query = self._filter_deleted(query)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get lead by phone: {e}")
            return None
    
    async def get_or_create_lead(
        self,
        email: str = None,
        phone: str = None,
        name: str = "Unknown",
        **kwargs
    ):
        """Get existing lead or create new"""
        try:
            lead = None
            
            if email:
                lead = await self.get_lead_by_email(email)
            
            if not lead and phone:
                lead = await self.get_lead_by_phone(phone)
            
            if not lead:
                lead = await self.add_lead(
                    name=name,
                    email=email or f"unknown_{phone}@temp.com",
                    phone=phone or "+00000000000",
                    **kwargs
                )
                logger.info(f"New lead created: {lead.id}")
            else:
                logger.debug(f"Existing lead found: {lead.id}")
            
            return lead
        except Exception as e:
            logger.error(f"Failed to get_or_create lead: {e}")
            raise

    async def update_lead(self, lead_id: int, updates: dict):
        """Update lead fields"""
        try:
            lead = await self.get_lead_by_id(lead_id)
            if not lead:
                logger.warning(f"Cannot update - lead not found: {lead_id}")
                return None
            
            for key, value in updates.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
            
            await self.session.commit()
            await self.session.refresh(lead)
            
            logger.info(f"Lead updated: {lead_id} - fields: {list(updates.keys())}")
            return lead
        except Exception as e:
            logger.error(f"Failed to update lead {lead_id}: {e}")
            await self.session.rollback()
            raise

    async def soft_delete_lead(self, lead_id: int):
        """Soft delete lead"""
        try:
            lead = await self.get_lead_by_id(lead_id)
            if lead:
                lead.soft_delete()
                await self.session.commit()
                logger.info(f"Lead soft deleted: {lead_id}")
            return lead
        except Exception as e:
            logger.error(f"Failed to soft delete lead {lead_id}: {e}")
            await self.session.rollback()
            raise

    async def update_lead_engagement(self, lead_id: int):
        """Update engagement metrics (denormalized)"""
        try:
            lead = await self.get_lead_by_id(lead_id)
            if lead:
                lead.message_count += 1
                lead.last_contacted_at = datetime.utcnow()
                await self.session.commit()
                logger.debug(f"Engagement updated for lead: {lead_id}")
        except Exception as e:
            logger.error(f"Failed to update engagement: {e}")

    # ============================================================================
    # CONVERSATION CRUD
    # ============================================================================
    
    async def add_conversation(
        self,
        lead_id: int,
        message: str,
        channel: str,
        sender: str = "user",
        parent_message_id: int = None,
        message_id: str = None,
        intent_detected: str = None,
        cost: float = 0.0,
        campaign_id: int = None
    ):
        """Create conversation record"""
        try:
            conv = Conversation(
                lead_id=lead_id,
                message=message,
                channel=channel,
                sender=sender,
                parent_message_id=parent_message_id,
                message_id=message_id,
                intent_detected=intent_detected,
                cost=cost,
                campaign_id=campaign_id,
                delivery_status="sent" if sender == "ai" else "received"
            )
            self.session.add(conv)
            await self.session.commit()
            await self.session.refresh(conv)
            
            # Update lead engagement
            await self.update_lead_engagement(lead_id)
            
            logger.info(f"Conversation saved: lead={lead_id}, channel={channel}, sender={sender}")
            return conv
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            await self.session.rollback()
            raise

    async def create_conversation(self, data: dict):
        """Wrapper accepting dict"""
        return await self.add_conversation(
            lead_id=data["lead_id"],
            message=data["message"],
            channel=data.get("channel", "unknown"),
            sender=data.get("sender", "user"),
            message_id=data.get("message_id"),
            intent_detected=data.get("intent"),
            cost=data.get("cost", 0.0)
        )

    async def save_conversation(self, data: dict):
        """Alias for create_conversation"""
        return await self.create_conversation(data)

    async def get_conversations_by_lead(
        self,
        lead_id: int,
        limit: int = 50,
        include_deleted: bool = False
    ):
        """Get conversations for lead"""
        try:
            query = select(Conversation).filter_by(lead_id=lead_id)
            if not include_deleted:
                query = self._filter_deleted(query)
            
            query = query.order_by(desc(Conversation.timestamp)).limit(limit)
            result = await self.session.execute(query)
            conversations = result.scalars().all()
            
            logger.debug(f"Retrieved {len(conversations)} conversations for lead {lead_id}")
            return list(reversed(conversations))
        except Exception as e:
            logger.error(f"Failed to get conversations for lead {lead_id}: {e}")
            return []

    async def get_conversation_by_message_id(self, message_id: str):
        """Find conversation by external message ID"""
        try:
            query = select(Conversation).filter_by(message_id=message_id)
            query = self._filter_deleted(query)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get conversation by message_id: {e}")
            return None

    async def update_delivery_status(
        self,
        conversation_id: int,
        status: str
    ):
        """Update message delivery status"""
        try:
            conv = await self.session.get(Conversation, conversation_id)
            if conv:
                conv.delivery_status = status
                await self.session.commit()
                logger.debug(f"Delivery status updated: {conversation_id} -> {status}")
            return conv
        except Exception as e:
            logger.error(f"Failed to update delivery status: {e}")
            return None

    # ============================================================================
    # FOLLOW-UP CRUD
    # ============================================================================
    
    async def create_followup(
        self,
        lead_id: int,
        scheduled_time: datetime,
        followup_type: str,
        channel: str,
        message_template: str = None
    ):
        """Create follow-up task"""
        try:
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
            
            logger.info(f"Follow-up created: lead={lead_id}, time={scheduled_time}, type={followup_type}")
            return followup
        except Exception as e:
            logger.error(f"Failed to create follow-up: {e}")
            await self.session.rollback()
            raise
    
    async def get_pending_followups(self, limit: int = 50):
        """Get due follow-ups"""
        try:
            now = datetime.utcnow()
            query = select(FollowUp).filter(
                and_(
                    FollowUp.status == "scheduled",
                    FollowUp.scheduled_time <= now,
                    FollowUp.is_deleted == False
                )
            ).order_by(FollowUp.scheduled_time).limit(limit)
            
            result = await self.session.execute(query)
            followups = result.scalars().all()
            
            logger.info(f"Retrieved {len(followups)} pending follow-ups")
            return followups
        except Exception as e:
            logger.error(f"Failed to get pending follow-ups: {e}")
            return []
    
    async def update_followup_status(self, followup_id: int, status: str):
        """Update follow-up status"""
        try:
            followup = await self.session.get(FollowUp, followup_id)
            if followup:
                followup.status = status
                if status == "sent":
                    followup.sent_at = datetime.utcnow()
                await self.session.commit()
                logger.info(f"Follow-up status updated: {followup_id} -> {status}")
            return followup
        except Exception as e:
            logger.error(f"Failed to update follow-up status: {e}")
            return None

    # ============================================================================
    # MESSAGE QUEUE CRUD
    # ============================================================================
    
    async def enqueue_message(
        self,
        lead_id: int,
        channel: str,
        message_data: dict,
        priority: int = 5
    ):
        """Add message to queue"""
        try:
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
            
            logger.info(f"Message queued: lead={lead_id}, channel={channel}, priority={priority}")
            return queue_item
        except Exception as e:
            logger.error(f"Failed to enqueue message: {e}")
            await self.session.rollback()
            raise
    
    async def get_pending_messages(self, limit: int = 10):
        """Get pending messages from queue"""
        try:
            query = select(MessageQueue).filter_by(
                status="pending",
                is_deleted=False
            ).order_by(
                MessageQueue.priority,
                MessageQueue.created_at
            ).limit(limit)
            
            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get pending messages: {e}")
            return []
    
    async def update_queue_status(
        self,
        queue_id: int,
        status: str,
        error_message: str = None
    ):
        """Update queue item status"""
        try:
            queue_item = await self.session.get(MessageQueue, queue_id)
            if queue_item:
                queue_item.status = status
                queue_item.processed_at = datetime.utcnow()
                if error_message:
                    queue_item.error_message = error_message
                    queue_item.retry_count += 1
                await self.session.commit()
                logger.debug(f"Queue status updated: {queue_id} -> {status}")
            return queue_item
        except Exception as e:
            logger.error(f"Failed to update queue status: {e}")
            return None

    # ============================================================================
    # EMAIL MESSAGE CRUD
    # ============================================================================
    
    async def save_email_message(
        self,
        conversation_id: int,
        subject: str,
        body_html: str,
        body_text: str,
        from_email: str,
        to_email: str,
        thread_id: str = None,
        in_reply_to: str = None
    ):
        """Save full email details"""
        try:
            email_msg = EmailMessage(
                conversation_id=conversation_id,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                from_email=from_email,
                to_email=to_email,
                thread_id=thread_id,
                in_reply_to=in_reply_to
            )
            self.session.add(email_msg)
            await self.session.commit()
            
            logger.info(f"Email message saved: conversation={conversation_id}, subject={subject[:50]}")
            return email_msg
        except Exception as e:
            logger.error(f"Failed to save email message: {e}")
            await self.session.rollback()
            raise

    # ============================================================================
    # ATTACHMENT CRUD
    # ============================================================================
    
    async def save_attachment(
        self,
        conversation_id: int,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_path: str
    ):
        """Save attachment metadata"""
        try:
            attachment = Attachment(
                conversation_id=conversation_id,
                filename=filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                storage_path=storage_path
            )
            self.session.add(attachment)
            await self.session.commit()
            
            logger.info(f"Attachment saved: {filename} ({size_bytes} bytes)")
            return attachment
        except Exception as e:
            logger.error(f"Failed to save attachment: {e}")
            await self.session.rollback()
            raise

    # ============================================================================
    # ORGANIZATION CRUD
    # ============================================================================
    
    async def get_or_create_organization(
        self,
        name: str,
        domain: str = None,
        **kwargs
    ):
        """Get or create organization"""
        try:
            query = select(Organization).filter_by(name=name, is_deleted=False)
            result = await self.session.execute(query)
            org = result.scalar_one_or_none()
            
            if not org:
                org = Organization(name=name, domain=domain, **kwargs)
                self.session.add(org)
                await self.session.commit()
                await self.session.refresh(org)
                logger.info(f"Organization created: {name}")
            else:
                logger.debug(f"Organization found: {name}")
            
            return org
        except Exception as e:
            logger.error(f"Failed to get_or_create organization: {e}")
            await self.session.rollback()
            raise

    # ============================================================================
    # CLIENT CRUD
    # ============================================================================
    
    async def convert_lead_to_client(
        self,
        lead_id: int,
        user_id: int,
        plan_type: str = None,
        mrr: float = 0.0
    ):
        """Convert lead to client"""
        try:
            lead = await self.get_lead_by_id(lead_id)
            if not lead:
                raise ValueError(f"Lead {lead_id} not found")
            
            client = Client(
                lead_id=lead_id,
                organization_id=lead.organization_id,
                user_id=user_id,
                whatsapp_number=lead.whatsapp_number,
                city=lead.city,
                country=lead.country,
                timezone=lead.timezone,
                plan_type=plan_type,
                mrr=mrr,
                onboarded_at=datetime.utcnow(),
                status="active"
            )
            self.session.add(client)
            
            # Update lead status
            lead.lead_status = "converted"
            
            await self.session.commit()
            await self.session.refresh(client)
            
            logger.info(f"Lead converted to client: lead={lead_id}, client={client.id}")
            return client
        except Exception as e:
            logger.error(f"Failed to convert lead to client: {e}")
            await self.session.rollback()
            raise

    # ============================================================================
    # CAMPAIGN CRUD
    # ============================================================================
    
    async def get_campaign_by_id(self, campaign_id: int):
        """Get campaign"""
        try:
            query = select(Campaign).filter_by(id=campaign_id, is_deleted=False)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get campaign {campaign_id}: {e}")
            return None

    # ============================================================================
    # USER CRUD
    # ============================================================================
    
    async def get_user_by_username(self, username: str):
        """Get user by username"""
        try:
            query = select(User).filter_by(username=username, is_deleted=False)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get user {username}: {e}")
            return None

    # ============================================================================
    # SUPPORT TICKET CRUD
    # ============================================================================
    
    async def create_support_ticket(
        self,
        client_id: int,
        subject: str,
        priority: str = "medium",
        conversation_id: int = None
    ):
        """Create support ticket"""
        try:
            # Generate ticket number
            count = await self.session.execute(
                select(func.count(SupportTicket.id))
            )
            ticket_number = f"TICKET-{count.scalar() + 1:06d}"
            
            ticket = SupportTicket(
                client_id=client_id,
                conversation_id=conversation_id,
                ticket_number=ticket_number,
                subject=subject,
                priority=priority,
                status="open"
            )
            self.session.add(ticket)
            await self.session.commit()
            await self.session.refresh(ticket)
            
            logger.info(f"Support ticket created: {ticket_number} for client {client_id}")
            return ticket
        except Exception as e:
            logger.error(f"Failed to create support ticket: {e}")
            await self.session.rollback()
            raise
    
    async def get_ticket_by_number(self, ticket_number: str):
        """Get ticket by number"""
        try:
            query = select(SupportTicket).filter_by(
                ticket_number=ticket_number,
                is_deleted=False
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get ticket {ticket_number}: {e}")
            return None
    
    async def update_ticket_status(
        self,
        ticket_id: int,
        status: str,
        assigned_to: int = None
    ):
        """Update ticket status"""
        try:
            ticket = await self.session.get(SupportTicket, ticket_id)
            if ticket:
                ticket.status = status
                if assigned_to:
                    ticket.assigned_to = assigned_to
                if status in ["resolved", "closed"]:
                    ticket.resolved_at = datetime.utcnow()
                await self.session.commit()
                logger.info(f"Ticket updated: {ticket.ticket_number} -> {status}")
            return ticket
        except Exception as e:
            logger.error(f"Failed to update ticket: {e}")
            return None
    
    async def get_open_tickets_for_client(self, client_id: int):
        """Get open tickets for client"""
        try:
            query = select(SupportTicket).filter(
                and_(
                    SupportTicket.client_id == client_id,
                    SupportTicket.status.in_(["open", "in_progress"]),
                    SupportTicket.is_deleted == False
                )
            ).order_by(desc(SupportTicket.created_at))
            
            result = await self.session.execute(query)
            tickets = result.scalars().all()
            
            logger.debug(f"Retrieved {len(tickets)} open tickets for client {client_id}")
            return tickets
        except Exception as e:
            logger.error(f"Failed to get tickets for client {client_id}: {e}")
            return []