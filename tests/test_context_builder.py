"""
Context Builder Tests
"""

import pytest
from utils.context_builder import ContextBuilder
from database.crud import DBManager


@pytest.mark.asyncio
async def test_build_context_new_lead(db_manager: DBManager):
    """Test building context for new lead"""
    context_builder = ContextBuilder(db_manager)
    
    context = await context_builder.build_context_for_ai(
        lead_id=999,  # Non-existent
        current_message="Hello",
        channel="sms"
    )
    
    assert context['conversation_type'] == 'new'
    assert context['conversation_history'] == []


@pytest.mark.asyncio
async def test_build_context_existing_lead(db_manager: DBManager, sample_lead):
    """Test building context for existing lead"""
    # Add some conversation history
    await db_manager.add_conversation(
        lead_id=sample_lead.id,
        message="Previous message",
        channel="sms",
        sender="user"
    )
    
    context_builder = ContextBuilder(db_manager)
    
    context = await context_builder.build_context_for_ai(
        lead_id=sample_lead.id,
        current_message="Follow up message",
        channel="sms"
    )
    
    assert context['conversation_type'] == 'continuation'
    assert len(context['conversation_history']) > 0
    assert context['lead_info']['name'] == sample_lead.name


@pytest.mark.asyncio
async def test_format_context_for_llm(db_manager: DBManager, sample_lead):
    """Test formatting context for LLM prompt"""
    context_builder = ContextBuilder(db_manager)
    
    context = await context_builder.build_context_for_ai(
        lead_id=sample_lead.id,
        current_message="Test message",
        channel="email"
    )
    
    formatted = context_builder.format_context_for_llm_prompt(context)
    
    assert isinstance(formatted, str)
    assert "CUSTOMER INFORMATION" in formatted
    assert sample_lead.name in formatted
    assert "Test message" in formatted