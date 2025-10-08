from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.db import Base

class BaseModel(Base):
    __abstract__ = True

    def __str__(self):
        fields = ", ".join(f"{k}={getattr(self, k)}" for k in self.__table__.columns.keys())
        return f"<{self.__class__.__name__}({fields})>"

class Lead(BaseModel):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String, nullable=False, unique=True)
    client_type = Column(String, nullable=True)
    preferred_channel = Column(String, nullable=True)  # call/email/sms/whatsapp
    next_action_time = Column(DateTime, nullable=True)
    pending_action = Column(String, nullable=True)
    lead_status = Column(String, default="new")  # new/contacted/qualified/converted/closed
    last_contacted_at = Column(DateTime, nullable=True)
    extra_data = Column(JSON, nullable=True)
    
    # NEW FIELDS
    last_message_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=0)
    response_received = Column(Boolean, default=False)
    followup_count = Column(Integer, default=0)
    last_followup_at = Column(DateTime, nullable=True)

    conversations = relationship(
        "Conversation", back_populates="lead", cascade="all, delete-orphan"
    )
    
    followups = relationship(
        "FollowUp", back_populates="lead", cascade="all, delete-orphan"
    )

class Conversation(BaseModel):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    message = Column(Text, nullable=False)
    channel = Column(String, nullable=False)  # call/email/sms/whatsapp
    sender = Column(String, nullable=False)  # user/ai/system
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # NEW FIELDS FOR THREADING
    parent_message_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    message_id = Column(String, nullable=True)  # External ID from service (Twilio SID, Email Message-ID)
    delivery_status = Column(String, default="pending")  # pending/sent/delivered/failed/read
    read_at = Column(DateTime, nullable=True)
    
    # METADATA
    intent_detected = Column(String, nullable=True)
    embedding_id = Column(String, nullable=True)
    meta_data = Column(JSON, nullable=True)  # Store extra info like attachments, media URLs

    lead = relationship("Lead", back_populates="conversations")
    
    # Self-referential relationship for threading
    parent = relationship("Conversation", remote_side=[id], backref="replies")


class FollowUp(BaseModel):
    __tablename__ = "followups"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    scheduled_time = Column(DateTime, nullable=False)
    followup_type = Column(String, nullable=False)  # reminder/nurture/escalation
    channel = Column(String, nullable=False)  # email/sms/whatsapp/call
    status = Column(String, default="scheduled")  # scheduled/sent/completed/cancelled
    message_template = Column(String, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="followups")


class MessageQueue(BaseModel):
    __tablename__ = "message_queue"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    channel = Column(String, nullable=False)
    message_data = Column(JSON, nullable=False)  # Store full message payload
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    status = Column(String, default="pending")  # pending/processing/completed/failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)