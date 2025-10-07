"""
Context Builder - Builds context for AI from conversation history
"""

from typing import List, Dict, Optional
from datetime import datetime
from database.crud import DBManager
from database.models import Lead, Conversation
from utils.thread_manager import ThreadManager


class ContextBuilder:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        self.thread_manager = ThreadManager(db_manager)
    
    async def build_context_for_ai(
        self,
        lead_id: int,
        current_message: str,
        channel: str,
        max_messages: int = 10
    ) -> Dict:
        """
        Build complete context for AI including conversation history and metadata
        
        Args:
            lead_id: Lead ID
            current_message: Current message from user
            channel: Communication channel (call/email/sms/whatsapp)
            max_messages: Maximum conversation history to include
        
        Returns:
            Dictionary with complete context for AI
        """
        # Get lead information
        lead = await self.db.get_lead_by_id(lead_id)
        if not lead:
            return self._create_empty_context(current_message, channel)
        
        # Get conversation history
        conversations = await self.db.get_conversations_by_lead(
            lead_id,
            limit=max_messages
        )
        
        # Get thread context
        thread_context = await self.thread_manager.identify_thread_context(
            lead_id,
            current_message,
            channel
        )
        
        # Format conversation history
        formatted_history = self._format_conversation_history(conversations)
        
        # Build lead metadata
        lead_metadata = self._build_lead_metadata(lead)
        
        # Determine conversation type
        conversation_type = self._determine_conversation_type(
            lead,
            thread_context
        )
        
        # Build complete context
        context = {
            'lead_id': lead_id,
            'lead_info': lead_metadata,
            'current_message': current_message,
            'channel': channel,
            'conversation_history': formatted_history,
            'conversation_type': conversation_type,
            'thread_context': thread_context,
            'timestamp': datetime.now().isoformat()
        }
        
        return context
    
    def _format_conversation_history(
        self,
        conversations: List[Conversation]
    ) -> List[Dict]:
        """Format conversations for AI consumption"""
        formatted = []
        
        for conv in conversations:
            formatted.append({
                'timestamp': conv.timestamp.isoformat() if conv.timestamp else None,
                'channel': conv.channel,
                'sender': conv.sender,
                'message': conv.message,
                'intent': conv.intent_detected
            })
        
        return formatted
    
    def _build_lead_metadata(self, lead: Lead) -> Dict:
        """Extract relevant lead metadata"""
        return {
            'name': lead.name,
            'email': lead.email,
            'phone': lead.phone,
            'client_type': lead.client_type,
            'lead_status': lead.lead_status,
            'preferred_channel': lead.preferred_channel,
            'last_contacted_at': lead.last_contacted_at.isoformat() if lead.last_contacted_at else None,
            'message_count': lead.message_count,
            'followup_count': lead.followup_count
        }
    
    def _determine_conversation_type(
        self,
        lead: Lead,
        thread_context: Dict
    ) -> str:
        """
        Determine type of conversation
        
        Returns: 'new', 'continuation', 'revival', 'support'
        """
        if lead.message_count == 0:
            return 'new'
        
        if thread_context.get('thread_age_hours'):
            age = thread_context['thread_age_hours']
            if age < 24:
                return 'continuation'
            elif age < 168:  # 7 days
                return 'follow_up'
            else:
                return 'revival'
        
        if lead.lead_status == 'converted':
            return 'support'
        
        return 'continuation'
    
    def _create_empty_context(
        self,
        current_message: str,
        channel: str
    ) -> Dict:
        """Create context for new lead"""
        return {
            'lead_id': None,
            'lead_info': None,
            'current_message': current_message,
            'channel': channel,
            'conversation_history': [],
            'conversation_type': 'new',
            'thread_context': {
                'is_continuation': False,
                'last_channel': None,
                'last_intent': None,
                'conversation_count': 0
            },
            'timestamp': datetime.now().isoformat()
        }
    
    async def select_relevant_messages(
        self,
        conversations: List[Conversation],
        current_message: str,
        max_selected: int = 5
    ) -> List[Conversation]:
        """
        Select most relevant messages from history based on current message
        
        Uses simple keyword matching for now. Can be enhanced with embeddings.
        
        Args:
            conversations: All conversations
            current_message: Current user message
            max_selected: Maximum messages to select
        
        Returns:
            List of most relevant conversations
        """
        if len(conversations) <= max_selected:
            return conversations
        
        # Always include most recent messages
        recent = conversations[-3:] if len(conversations) >= 3 else conversations
        
        # Find relevant older messages
        keywords = self._extract_keywords(current_message)
        relevant_old = []
        
        for conv in conversations[:-3]:
            if any(keyword.lower() in conv.message.lower() for keyword in keywords):
                relevant_old.append(conv)
        
        # Combine recent + relevant old
        selected = list(recent)
        remaining_slots = max_selected - len(selected)
        
        if remaining_slots > 0 and relevant_old:
            selected = relevant_old[-remaining_slots:] + selected
        
        return selected
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Simple implementation - extract words longer than 3 chars
        words = text.split()
        keywords = [w for w in words if len(w) > 3]
        return keywords[:5]  # Top 5 keywords
    
    def format_context_for_llm_prompt(self, context: Dict) -> str:
        """
        Format context into text prompt for LLM
        
        Args:
            context: Context dictionary from build_context_for_ai
        
        Returns:
            Formatted string for LLM prompt
        """
        prompt_parts = []
        
        # Lead information
        if context['lead_info']:
            lead_info = context['lead_info']
            prompt_parts.append(f"CUSTOMER INFORMATION:")
            prompt_parts.append(f"- Name: {lead_info['name']}")
            prompt_parts.append(f"- Contact: {lead_info['email']}, {lead_info['phone']}")
            prompt_parts.append(f"- Type: {lead_info['client_type']}")
            prompt_parts.append(f"- Status: {lead_info['lead_status']}")
            prompt_parts.append(f"- Previous contacts: {lead_info['message_count']}")
            prompt_parts.append("")
        
        # Conversation type
        prompt_parts.append(f"CONVERSATION TYPE: {context['conversation_type']}")
        prompt_parts.append(f"CURRENT CHANNEL: {context['channel']}")
        prompt_parts.append("")
        
        # Conversation history
        if context['conversation_history']:
            prompt_parts.append("CONVERSATION HISTORY:")
            for i, msg in enumerate(context['conversation_history'], 1):
                timestamp = msg['timestamp']
                sender = msg['sender'].upper()
                channel = msg['channel']
                message = msg['message']
                
                prompt_parts.append(f"{i}. [{timestamp}, {channel}] {sender}: {message}")
            prompt_parts.append("")
        
        # Current message
        prompt_parts.append(f"CURRENT MESSAGE ({context['channel']}): {context['current_message']}")
        prompt_parts.append("")
        
        return "\n".join(prompt_parts)
    
    async def get_context_summary(self, lead_id: int) -> str:
        """
        Get a brief summary of conversation context
        
        Args:
            lead_id: Lead ID
        
        Returns:
            Brief text summary
        """
        lead = await self.db.get_lead_by_id(lead_id)
        if not lead:
            return "New customer, no previous history."
        
        conversations = await self.db.get_conversations_by_lead(lead_id, limit=10)
        
        summary_parts = []
        summary_parts.append(f"Customer: {lead.name} ({lead.client_type})")
        summary_parts.append(f"Status: {lead.lead_status}")
        summary_parts.append(f"Total messages: {lead.message_count}")
        
        if conversations:
            last_conv = conversations[-1]
            time_ago = self._time_ago(last_conv.timestamp)
            summary_parts.append(f"Last contact: {time_ago} via {last_conv.channel}")
            
            if last_conv.intent_detected:
                summary_parts.append(f"Last intent: {last_conv.intent_detected}")
        
        return " | ".join(summary_parts)
    
    def _time_ago(self, timestamp: datetime) -> str:
        """Convert timestamp to human-readable 'time ago' format"""
        now = datetime.now()
        diff = now - timestamp
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"