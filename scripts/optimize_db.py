"""
Database Optimization Script - Add indexes and optimize queries
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import engine


async def create_indexes():
    """Create performance indexes"""
    
    indexes = [
        # Conversations indexes
        """CREATE INDEX IF NOT EXISTS idx_conversations_lead_timestamp 
           ON conversations(lead_id, timestamp DESC)""",
        
        """CREATE INDEX IF NOT EXISTS idx_conversations_channel_timestamp 
           ON conversations(channel, timestamp DESC)""",
        
        """CREATE INDEX IF NOT EXISTS idx_conversations_sender_timestamp 
           ON conversations(sender, timestamp DESC)""",
        
        """CREATE INDEX IF NOT EXISTS idx_conversations_intent 
           ON conversations(intent_detected)""",
        
        # Leads indexes
        """CREATE INDEX IF NOT EXISTS idx_leads_status 
           ON leads(lead_status)""",
        
        """CREATE INDEX IF NOT EXISTS idx_leads_last_contacted 
           ON leads(last_contacted_at DESC)""",
        
        """CREATE INDEX IF NOT EXISTS idx_leads_response 
           ON leads(response_received, last_contacted_at DESC)""",
        
        # Follow-ups indexes
        """CREATE INDEX IF NOT EXISTS idx_followups_scheduled 
           ON followups(scheduled_time, status)""",
        
        """CREATE INDEX IF NOT EXISTS idx_followups_lead_status 
           ON followups(lead_id, status)""",
        
        # Message queue indexes
        """CREATE INDEX IF NOT EXISTS idx_queue_status_priority 
           ON message_queue(status, priority, created_at)"""
    ]
    
    print("\n" + "=" * 60)
    print("DATABASE OPTIMIZATION")
    print("=" * 60 + "\n")
    
    async with engine.begin() as conn:
        for idx, index_sql in enumerate(indexes, 1):
            try:
                print(f"Creating index {idx}/{len(indexes)}...")
                await conn.execute(index_sql)
                print(f"✅ Index {idx} created")
            except Exception as e:
                print(f"⚠️ Index {idx} failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ DATABASE OPTIMIZATION COMPLETE")
    print("=" * 60 + "\n")


async def analyze_database():
    """Analyze database statistics"""
    
    print("\n" + "=" * 60)
    print("DATABASE ANALYSIS")
    print("=" * 60 + "\n")
    
    queries = {
        'Total Leads': "SELECT COUNT(*) FROM leads",
        'Total Conversations': "SELECT COUNT(*) FROM conversations",
        'Conversations by Channel': """
            SELECT channel, COUNT(*) as count 
            FROM conversations 
            GROUP BY channel
        """,
        'Leads by Status': """
            SELECT lead_status, COUNT(*) as count 
            FROM leads 
            GROUP BY lead_status
        """
    }
    
    async with engine.begin() as conn:
        for name, query in queries.items():
            try:
                result = await conn.execute(query)
                rows = result.fetchall()
                
                print(f"{name}:")
                for row in rows:
                    print(f"  {row}")
                print()
            except Exception as e:
                print(f"❌ Query failed: {e}\n")
    
    print("=" * 60 + "\n")


async def main():
    """Main function"""
    print("\nDatabase Optimization Options:")
    print("1. Create indexes")
    print("2. Analyze database")
    print("3. Both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        await create_indexes()
    elif choice == '2':
        await analyze_database()
    elif choice == '3':
        await create_indexes()
        await analyze_database()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())