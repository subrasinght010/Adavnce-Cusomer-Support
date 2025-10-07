"""
Database Tests - Test CRUD operations
"""

import pytest
from datetime import datetime
from database.crud import DBManager


@pytest.mark.asyncio
async def test_create_lead(db_manager: DBManager):
    """Test lead creation"""
    lead = await db_manager.add_lead(
        name="John Doe",
        email="john@example.com",
        phone="+1234567890"
    )
    
    assert lead.id is not None
    assert lead.name == "John Doe"
    assert lead.email == "john@example.com"
    assert lead.phone == "+1234567890"


@pytest.mark.asyncio
async def test_get_lead_by_email(db_manager: DBManager, sample_lead):
    """Test getting lead by email"""
    lead = await db_manager.get_lead_by_email(sample_lead.email)
    
    assert lead is not None
    assert lead.id == sample_lead.id
    assert lead.email == sample_lead.email


@pytest.mark.asyncio
async def test_get_lead_by_phone(db_manager: DBManager, sample_lead):
    """Test getting lead by phone"""
    lead = await db_manager.get_lead_by_phone(sample_lead.phone)
    
    assert lead is not None
    assert lead.id == sample_lead.id
    assert lead.phone == sample_lead.phone


@pytest.mark.asyncio
async def test_add_conversation(db_manager: DBManager, sample_lead):
    """Test adding conversation"""
    conv = await db_manager.add_conversation(
        lead_id=sample_lead.id,
        message="Test message",
        channel="sms",
        sender="user"
    )
    
    assert conv.id is not None
    assert conv.lead_id == sample_lead.id
    assert conv.message == "Test message"
    assert conv.channel == "sms"
    assert conv.sender == "user"


@pytest.mark.asyncio
async def test_conversation_threading(db_manager: DBManager, sample_lead):
    """Test conversation threading"""
    # Create parent conversation
    parent = await db_manager.add_conversation(
        lead_id=sample_lead.id,
        message="User question",
        channel="email",
        sender="user",
        message_id="msg_123"
    )
    
    # Create reply
    reply = await db_manager.add_conversation(
        lead_id=sample_lead.id,
        message="AI response",
        channel="email",
        sender="ai",
        parent_message_id=parent.id,
        message_id="msg_456"
    )
    
    assert reply.parent_message_id == parent.id
    
    # Test finding parent
    found_parent = await db_manager.find_parent_message("msg_456")
    assert found_parent is not None
    assert found_parent.id == parent.id


@pytest.mark.asyncio
async def test_get_conversations_by_lead(db_manager: DBManager, sample_lead):
    """Test getting all conversations for a lead"""
    # Create multiple conversations
    for i in range(3):
        await db_manager.add_conversation(
            lead_id=sample_lead.id,
            message=f"Message {i}",
            channel="sms",
            sender="user"
        )
    
    # Get conversations
    convs = await db_manager.get_conversations_by_lead(sample_lead.id)
    
    assert len(convs) == 3
    assert convs[0].message == "Message 0"
    assert convs[-1].message == "Message 2"


@pytest.mark.asyncio
async def test_create_followup(db_manager: DBManager, sample_lead):
    """Test creating follow-up"""
    scheduled_time = datetime.now()
    
    followup = await db_manager.create_followup(
        lead_id=sample_lead.id,
        scheduled_time=scheduled_time,
        followup_type="reminder",
        channel="email"
    )
    
    assert followup.id is not None
    assert followup.lead_id == sample_lead.id
    assert followup.followup_type == "reminder"
    assert followup.status == "scheduled"


@pytest.mark.asyncio
async def test_get_pending_followups(db_manager: DBManager, sample_lead):
    """Test getting pending follow-ups"""
    # Create past follow-up (should be returned)
    past_time = datetime.now()
    await db_manager.create_followup(
        lead_id=sample_lead.id,
        scheduled_time=past_time,
        followup_type="reminder",
        channel="sms"
    )
    
    # Get pending
    pending = await db_manager.get_pending_followups()
    
    assert len(pending) >= 1
    assert pending[0].status == "scheduled"


@pytest.mark.asyncio
async def test_update_delivery_status(db_manager: DBManager, sample_lead):
    """Test updating delivery status"""
    # Create conversation
    conv = await db_manager.add_conversation(
        lead_id=sample_lead.id,
        message="Test",
        channel="sms",
        sender="ai"
    )
    
    # Update status
    updated = await db_manager.update_delivery_status(
        conv.id,
        "delivered"
    )
    
    assert updated is not None
    assert updated.delivery_status == "delivered"


@pytest.mark.asyncio
async def test_get_or_create_lead_existing(db_manager: DBManager, sample_lead):
    """Test get_or_create with existing lead"""
    lead = await db_manager.get_or_create_lead(
        email=sample_lead.email,
        phone=sample_lead.phone
    )
    
    assert lead.id == sample_lead.id


@pytest.mark.asyncio
async def test_get_or_create_lead_new(db_manager: DBManager):
    """Test get_or_create with new lead"""
    lead = await db_manager.get_or_create_lead(
        email="new@example.com",
        phone="+9876543210",
        name="New User"
    )
    
    assert lead.id is not None
    assert lead.email == "new@example.com"
    assert lead.name == "New User"