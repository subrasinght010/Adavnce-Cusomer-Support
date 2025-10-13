from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Boolean, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.db import Base

class BaseModel(Base):
    __abstract__ = True

    # Default fields for all tables
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete
    is_deleted = Column(Boolean, default=False, index=True)  # Soft delete flag

    def __str__(self):
        fields = ", ".join(f"{k}={getattr(self, k)}" for k in self.__table__.columns.keys())
        return f"<{self.__class__.__name__}({fields})>"
    
    def soft_delete(self):
        """Mark as deleted without removing from DB"""
        from datetime import datetime
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Restore soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None


# ============================================================================
# CORE TABLES
# ============================================================================

class Lead(BaseModel):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String, nullable=False, unique=True)
    
    # Basic info
    client_type = Column(String, nullable=True)
    preferred_channel = Column(String, nullable=True)
    lead_status = Column(String, default="new")  # new/contacted/qualified/converted/closed
    
    # Scheduling
    next_action_time = Column(DateTime, nullable=True)
    pending_action = Column(String, nullable=True)
    last_contacted_at = Column(DateTime, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    last_followup_at = Column(DateTime, nullable=True)
    
    # DENORMALIZED - Engagement metrics
    message_count = Column(Integer, default=0)
    response_received = Column(Boolean, default=False)
    followup_count = Column(Integer, default=0)
    total_conversations = Column(Integer, default=0)
    engagement_score = Column(Integer, default=0)  # 0-100
    
    # DENORMALIZED - Analytics
    total_cost = Column(Float, default=0.0)  # Total LLM cost
    last_intent = Column(String, nullable=True)
    last_sentiment = Column(String, nullable=True)
    
    # Attribution
    source = Column(String, nullable=True)  # google/facebook/referral
    utm_json = Column(JSON, nullable=True)  # {campaign, source, medium}
    
    # Extra
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversations = relationship("Conversation", back_populates="lead", cascade="all, delete-orphan")
    followups = relationship("FollowUp", back_populates="lead", cascade="all, delete-orphan")
    handoffs = relationship("HandoffQueue", back_populates="lead", cascade="all, delete-orphan")


class Conversation(BaseModel):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    
    # Content
    message = Column(Text, nullable=False)
    channel = Column(String, nullable=False)  # email/sms/whatsapp/call
    sender = Column(String, nullable=False)  # user/ai/system
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime, nullable=True)

    # Threading
    parent_message_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    message_id = Column(String, nullable=True)  # External ID (Twilio SID, Email Message-ID)
    
    # Status
    delivery_status = Column(String, default="pending")  # pending/sent/delivered/failed/read
    
    # DENORMALIZED - AI metadata
    intent_detected = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    embedding_id = Column(String, nullable=True)
    
    # DENORMALIZED - Performance
    cost = Column(Float, default=0.0)  # LLM cost for this message
    processing_time_ms = Column(Integer, nullable=True)
    kb_used = Column(Boolean, default=False)
    kb_doc_ids = Column(String, nullable=True)  # comma-separated for speed
    
    # Campaign tracking
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    campaign_touch_number = Column(Integer, nullable=True)
    
    # Extra
    meta_data = Column(JSON, nullable=True)

    # Relationships
    lead = relationship("Lead", back_populates="conversations")
    parent = relationship("Conversation", remote_side=[id], backref="replies")
    email_message = relationship("EmailMessage", back_populates="conversation", uselist=False)
    attachments = relationship("Attachment", back_populates="conversation", cascade="all, delete-orphan")
    campaign = relationship("Campaign", back_populates="conversations")


class FollowUp(BaseModel):
    __tablename__ = "followups"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    
    # Scheduling
    scheduled_time = Column(DateTime, nullable=False)
    followup_type = Column(String, nullable=False)  # reminder/nurture/escalation
    channel = Column(String, nullable=False)  # email/sms/whatsapp/call
    
    # Status
    status = Column(String, default="scheduled")  # scheduled/sent/completed/cancelled
    message_template = Column(String, nullable=True)
    
    # Execution
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    lead = relationship("Lead", back_populates="followups")


class MessageQueue(BaseModel):
    __tablename__ = "message_queue"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    
    # Message details
    channel = Column(String, nullable=False)
    message_data = Column(JSON, nullable=False)
    
    # Priority & retry
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    status = Column(String, default="pending")  # pending/processing/completed/failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime, nullable=True)


class User(BaseModel):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    email = Column(String, unique=True, nullable=True)
    role = Column(String, default="agent")  # admin/agent/viewer
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================================
# NEW TABLES
# ============================================================================

class EmailMessage(BaseModel):
    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), unique=True)
    
    # Email specific
    subject = Column(String, nullable=False)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    
    # Addresses
    from_email = Column(String, nullable=False)
    to_email = Column(String, nullable=False)
    cc = Column(String, nullable=True)  # comma-separated
    bcc = Column(String, nullable=True)
    
    # Threading
    thread_id = Column(String, nullable=True)
    references = Column(String, nullable=True)  # Message-IDs chain
    in_reply_to = Column(String, nullable=True)
    
    # Metadata
    headers_json = Column(JSON, nullable=True)
    raw_email_path = Column(String, nullable=True)  # Path to .eml file
    size_bytes = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="email_message")


class Attachment(BaseModel):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"))
    
    # File details
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    
    # Storage
    storage_path = Column(String, nullable=False)  # S3 or local path
    thumbnail_path = Column(String, nullable=True)
    
    # Security
    virus_scanned = Column(Boolean, default=False)
    scan_result = Column(String, nullable=True)
    
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="attachments")


class APILog(BaseModel):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Request details
    endpoint = Column(String, nullable=False, index=True)
    method = Column(String, nullable=False)  # GET/POST/etc
    
    # Payload
    request_json = Column(JSON, nullable=True)
    response_json = Column(JSON, nullable=True)
    
    # Result
    status_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    
    # Context
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class HandoffQueue(BaseModel):
    __tablename__ = "handoff_queue"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    
    # Escalation details
    reason = Column(String, nullable=False)  # complaint/complex_query/angry_customer
    priority = Column(String, default="medium")  # low/medium/high/urgent
    status = Column(String, default="queued")  # queued/assigned/resolved/cancelled
    
    # Assignment
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    lead = relationship("Lead", back_populates="handoffs")
    assigned_user = relationship("User")


class Campaign(BaseModel):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    
    # Campaign details
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    campaign_type = Column(String, nullable=False)  # cold/warm/nurture/reactivation
    
    # Sequence definition
    touch_sequence_json = Column(JSON, nullable=False)
    # Example: [
    #   {touch: 1, delay_hours: 0, channel: "email", template: "intro"},
    #   {touch: 2, delay_hours: 48, channel: "sms", template: "followup1"}
    # ]
    
    # Status
    active = Column(Boolean, default=True)
    
    # Analytics (denormalized)
    total_leads = Column(Integer, default=0)
    completed_sequences = Column(Integer, default=0)
    conversion_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    conversations = relationship("Conversation", back_populates="campaign")


# ============================================================================
# INDEXES FOR PERFORMANCE
# ============================================================================
# Add these in migration:
# CREATE INDEX idx_conversations_lead_timestamp ON conversations(lead_id, timestamp DESC);
# CREATE INDEX idx_conversations_channel_status ON conversations(channel, delivery_status);
# CREATE INDEX idx_followups_scheduled ON followups(scheduled_time, status);
# CREATE INDEX idx_api_logs_created ON api_logs(created_at DESC);
# CREATE INDEX idx_handoff_status ON handoff_queue(status, priority);