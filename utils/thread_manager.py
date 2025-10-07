"""
Thread Manager - Manages conversation threading across channels
"""

from typing import List, Dict, Optional, Tuple
from database.crud import DBManager
from database.models import Conversation
from datetime import datetime, timedelta
import re


class ThreadManager:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
    
    async def find_conversation_thread(
        self,
        lead_id: int,
        message_id: str = None,
        limit: int = 10
    ) -> List[Conversation]:
        """
        Find complete conversation thread for a lead
        
        Args:
            lead_id: Lead ID
            message_id: Optional message ID to find specific thread
            limit: Maximum messages to return
        
        Returns:
            List of conversations in chronological order
        """
        if message_id:
            # Find specific thread by message_id
            return await self._find_thread_by_message_id(message_id, limit)
        else:
            # Get all recent conversations
            return await self.db.get_conversations_by_lead(lead_id, limit)
    
    async def _find_thread_by_message_id(
        self,
        message_id: str,
        limit: int
    ) -> List[Conversation]:
        """Find thread starting from a specific message"""
        conversation = await self.db.get_conversation_by_message_id(message_id)
        
        if not conversation:
            return []
        
        # Get all conversations for this lead
        all_convs = await self.db.get_conversations_by_lead(
            conversation.lead_id,
            limit=limit
        )
        
        return all_convs
    
    async def get_parent_message(
        self,
        conversation: Conversation
    ) -> Optional[Conversation]:
        """Get parent message of a conversation"""
        if not conversation.parent_message_id:
            return None
        
        result = await self.db.session.execute(
            f"SELECT * FROM conversations WHERE id = {conversation.parent_message_id}"
        )
        return result.scalar_one_or_none()
    
    async def link_messages(
        self,
        child_message_id: int,
        parent_message_id: int
    ) -> bool:
        """Link a child message to its parent"""
        try:
            child = await self.db.session.get(Conversation, child_message_id)
            if child:
                child.parent_message_id = parent_message_id
                await self.db.session.commit()
                return True
            return False
        except Exception as e:
            print(f"❌ Error linking messages: {e}")
            return False
    
    def extract_email_thread_id(self, email_headers: Dict) -> Optional[str]:
        """
        Extract thread ID from email headers
        
        Args:
            email_headers: Dictionary of email headers
        
        Returns:
            Message-ID to use for threading
        """
        # Check In-Reply-To header first
        if 'In-Reply-To' in email_headers:
            return self._clean_message_id(email_headers['In-Reply-To'])
        
        # Check References header
        if 'References' in email_headers:
            # References contains space-separated list of message IDs
            references = email_headers['References'].strip().split()
            if references:
                # Return the first (original) message ID
                return self._clean_message_id(references[0])
        
        # No thread found
        return None
    
    def _clean_message_id(self, message_id: str) -> str:
        """Clean message ID by removing brackets"""
        return message_id.strip().strip('<>')
    
    async def build_full_thread(
        self,
        lead_id: int,
        include_channels: List[str] = None,
        hours: int = 168  # 7 days default
    ) -> List[Dict]:
        """
        Build complete conversation thread across all channels
        
        Args:
            lead_id: Lead ID
            include_channels: Optional list of channels to include
            hours: How far back to look (default 7 days)
        
        Returns:
            List of conversation dictionaries with metadata
        """
        conversations = await self.db.get_recent_conversations(
            lead_id,
            hours=hours,
            limit=100
        )
        
        thread = []
        for conv in conversations:
            # Filter by channel if specified
            if include_channels and conv.channel not in include_channels:
                continue
            
            thread.append({
                'id': conv.id,
                'message': conv.message,
                'channel': conv.channel,
                'sender': conv.sender,
                'timestamp': conv.timestamp,
                'parent_id': conv.parent_message_id,
                'message_id': conv.message_id,
                'intent': conv.intent_detected
            })
        
        return thread
    
    async def identify_thread_context(
        self,
        lead_id: int,
        current_message: str,
        channel: str
    ) -> Dict:
        """
        Identify thread context for current message
        
        Args:
            lead_id: Lead ID
            current_message: Current message text
            channel: Communication channel
        
        Returns:
            Dictionary with thread context
        """
        # Get recent conversations
        recent_convs = await self.db.get_recent_conversations(
            lead_id,
            hours=24,
            limit=5
        )
        
        context = {
            'is_continuation': len(recent_convs) > 0,
            'last_channel': recent_convs[0].channel if recent_convs else None,
            'last_intent': recent_convs[0].intent_detected if recent_convs else None,
            'conversation_count': len(recent_convs),
            'thread_age_hours': None
        }
        
        if recent_convs:
            time_diff = datetime.now() - recent_convs[0].timestamp
            context['thread_age_hours'] = time_diff.total_seconds() / 3600
        
        return context
    
    def determine_thread_freshness(
        self,
        last_message_time: datetime
    ) -> Tuple[bool, str]:
        """
        Determine if thread should be treated as fresh or continuation
        
        Args:
            last_message_time: Timestamp of last message
        
        Returns:
            Tuple of (is_fresh, reason)
        """
        now = datetime.now()
        time_diff = now - last_message_time
        hours = time_diff.total_seconds() / 3600
        
        if hours < 4:
            return (False, "Recent conversation (< 4 hours)")
        elif hours < 24:
            return (False, "Same day conversation")
        elif hours < 168:  # 7 days
            return (False, "Within a week")
        elif hours < 720:  # 30 days
            return (True, "Old conversation (> 1 week, < 30 days)")
        else:
            return (True, "Very old conversation (> 30 days)")