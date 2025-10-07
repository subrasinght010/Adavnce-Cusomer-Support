"""
Thread Manager Tests
"""

import pytest
from utils.thread_manager import ThreadManager
from database.crud import DBManager


@pytest.mark.asyncio
async def test_extract_email_thread_id():
    """Test extracting email thread ID from headers"""
    manager = ThreadManager(None)
    
    headers = {
        'In-Reply-To': '<msg-123@example.com>',
        'References': '<msg-123@example.com> <msg-456@example.com>'
    }
    
    thread_id = manager.extract_email_thread_id(headers)
    
    assert thread_id == 'msg-123@example.com'


@pytest.mark.asyncio
async def test_extract_email_thread_id_from_references():
    """Test extracting from References header only"""
    manager = ThreadManager(None)
    
    headers = {
        'References': '<msg-abc@example.com> <msg-def@example.com>'
    }
    
    thread_id = manager.extract_email_thread_id(headers)
    
    assert thread_id == 'msg-abc@example.com'


@pytest.mark.asyncio
async def test_determine_thread_freshness():
    """Test determining thread freshness"""
    from datetime import datetime, timedelta
    
    manager = ThreadManager(None)
    
    # Recent message (2 hours ago)
    recent_time = datetime.now() - timedelta(hours=2)
    is_fresh, reason = manager.determine_thread_freshness(recent_time)
    
    assert is_fresh is False
    assert "Recent" in reason
    
    # Old message (10 days ago)
    old_time = datetime.now() - timedelta(days=10)
    is_fresh, reason = manager.determine_thread_freshness(old_time)
    
    assert is_fresh is True
    assert "Old" in reason