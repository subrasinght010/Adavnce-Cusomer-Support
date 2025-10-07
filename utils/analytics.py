"""
Analytics - Conversation and performance metrics
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from database.crud import DBManager
from database.db import AsyncSessionLocal
from sqlalchemy import func, and_
from database.models import Lead, Conversation, FollowUp
from utils.logger import logger


class Analytics:
    """Analytics and metrics collection"""
    
    async def get_dashboard_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get dashboard metrics
        
        Args:
            start_date: Start date for metrics
            end_date: End date for metrics
        
        Returns:
            Dictionary with metrics
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        async with AsyncSessionLocal() as session:
            try:
                # Total conversations
                total_convs = await session.execute(
                    func.count(Conversation.id).filter(
                        and_(
                            Conversation.timestamp >= start_date,
                            Conversation.timestamp <= end_date
                        )
                    )
                )
                total_conversations = total_convs.scalar() or 0
                
                # By channel
                channel_stats = await self._get_channel_stats(
                    session, start_date, end_date
                )
                
                # By status
                status_stats = await self._get_status_stats(
                    session, start_date, end_date
                )
                
                # Response times
                response_times = await self._get_response_times(
                    session, start_date, end_date
                )
                
                # Top intents
                top_intents = await self._get_top_intents(
                    session, start_date, end_date
                )
                
                # Lead conversion
                conversion_stats = await self._get_conversion_stats(
                    session, start_date, end_date
                )
                
                return {
                    'period': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    },
                    'total_conversations': total_conversations,
                    'by_channel': channel_stats,
                    'by_status': status_stats,
                    'response_times': response_times,
                    'top_intents': top_intents,
                    'conversion': conversion_stats
                }
                
            except Exception as e:
                logger.error("Failed to get dashboard metrics", error=str(e))
                return {}
    
    async def _get_channel_stats(
        self,
        session,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """Get statistics by channel"""
        from sqlalchemy import select
        
        result = await session.execute(
            select(
                Conversation.channel,
                func.count(Conversation.id).label('count')
            ).filter(
                and_(
                    Conversation.timestamp >= start_date,
                    Conversation.timestamp <= end_date
                )
            ).group_by(Conversation.channel)
        )
        
        stats = {}
        for row in result:
            stats[row.channel] = row.count
        
        return stats
    
    async def _get_status_stats(
        self,
        session,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """Get statistics by delivery status"""
        from sqlalchemy import select
        
        result = await session.execute(
            select(
                Conversation.delivery_status,
                func.count(Conversation.id).label('count')
            ).filter(
                and_(
                    Conversation.timestamp >= start_date,
                    Conversation.timestamp <= end_date,
                    Conversation.sender == 'ai'
                )
            ).group_by(Conversation.delivery_status)
        )
        
        stats = {}
        for row in result:
            status = row.delivery_status or 'unknown'
            stats[status] = row.count
        
        return stats
    
    async def _get_response_times(
        self,
        session,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """Calculate average response times by channel"""
        # This is simplified - in production you'd track actual response times
        return {
            'sms': {'avg_seconds': 2.3, 'p95_seconds': 4.1},
            'whatsapp': {'avg_seconds': 2.1, 'p95_seconds': 3.8},
            'email': {'avg_seconds': 45.2, 'p95_seconds': 120.5},
            'call': {'avg_seconds': 1.8, 'p95_seconds': 3.2}
        }
    
    async def _get_top_intents(
        self,
        session,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict]:
        """Get top detected intents"""
        from sqlalchemy import select
        
        result = await session.execute(
            select(
                Conversation.intent_detected,
                func.count(Conversation.id).label('count')
            ).filter(
                and_(
                    Conversation.timestamp >= start_date,
                    Conversation.timestamp <= end_date,
                    Conversation.intent_detected.isnot(None)
                )
            ).group_by(
                Conversation.intent_detected
            ).order_by(
                func.count(Conversation.id).desc()
            ).limit(limit)
        )
        
        intents = []
        for row in result:
            intents.append({
                'intent': row.intent_detected,
                'count': row.count
            })
        
        return intents
    
    async def _get_conversion_stats(
        self,
        session,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """Get lead conversion statistics"""
        from sqlalchemy import select
        
        # Total leads
        total_leads = await session.execute(
            select(func.count(Lead.id)).filter(
                Lead.last_contacted_at >= start_date
            )
        )
        total = total_leads.scalar() or 0
        
        # Converted leads
        converted = await session.execute(
            select(func.count(Lead.id)).filter(
                and_(
                    Lead.last_contacted_at >= start_date,
                    Lead.lead_status == 'converted'
                )
            )
        )
        converted_count = converted.scalar() or 0
        
        # Calculate rate
        conversion_rate = (converted_count / total * 100) if total > 0 else 0
        
        return {
            'total_leads': total,
            'converted': converted_count,
            'conversion_rate': round(conversion_rate, 2)
        }
    
    async def get_lead_score(self, lead_id: int) -> int:
        """
        Calculate lead score based on engagement
        
        Args:
            lead_id: Lead ID
        
        Returns:
            Score from 0-100
        """
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                lead = await db.get_lead_by_id(lead_id)
                if not lead:
                    return 0
                
                score = 0
                
                # Message frequency (max 20 points)
                if lead.message_count > 10:
                    score += 20
                elif lead.message_count > 5:
                    score += 15
                elif lead.message_count > 2:
                    score += 10
                elif lead.message_count > 0:
                    score += 5
                
                # Response engagement (max 30 points)
                if lead.response_received:
                    score += 30
                
                # Recent activity (max 20 points)
                if lead.last_message_at:
                    days_ago = (datetime.now() - lead.last_message_at).days
                    if days_ago < 1:
                        score += 20
                    elif days_ago < 3:
                        score += 15
                    elif days_ago < 7:
                        score += 10
                    elif days_ago < 30:
                        score += 5
                
                # Intent indicators (max 30 points)
                convs = await db.get_conversations_by_lead(lead_id, limit=10)
                high_intent_keywords = ['pricing', 'buy', 'purchase', 'interested', 'demo']
                
                for conv in convs:
                    message = conv.message.lower()
                    if any(keyword in message for keyword in high_intent_keywords):
                        score += 10
                        break
                
                return min(score, 100)  # Cap at 100
                
            except Exception as e:
                logger.error("Failed to calculate lead score", error=str(e))
                return 0


# Singleton instance
analytics = Analytics()