"""
Follow-up Manager - Automated follow-up system
"""

import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from database.crud import DBManager
from database.db import AsyncSessionLocal
from database.models import Lead, FollowUp
from utils.context_builder import ContextBuilder
from tools.language_model import LanguageModel
from services.email_service import send_email
from services.sms_service import send_sms
from services.whatsapp_service import send_whatsapp
import os


class FollowUpManager:
    def __init__(self):
        self.check_interval = int(os.getenv('FOLLOWUP_CHECK_INTERVAL', '300'))  # 5 minutes
        self.email_delay = int(os.getenv('FOLLOWUP_EMAIL_DELAY', '86400'))  # 24 hours
        self.sms_delay = int(os.getenv('FOLLOWUP_SMS_DELAY', '172800'))  # 48 hours
        self.max_attempts = int(os.getenv('FOLLOWUP_MAX_ATTEMPTS', '3'))
        self.is_running = False
        self.llm = LanguageModel()
    
    async def start_monitoring(self):
        """Start follow-up monitoring loop"""
        self.is_running = True
        print(f"🔔 Follow-up manager started. Checking every {self.check_interval} seconds.")
        
        while self.is_running:
            try:
                await self.check_and_send_followups()
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                print(f"❌ Follow-up manager error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)
    
    def stop_monitoring(self):
        """Stop follow-up monitoring"""
        self.is_running = False
        print("🔔 Follow-up manager stopped.")
    
    async def check_and_send_followups(self):
        """Check for pending follow-ups and send them"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                # Get pending follow-ups
                pending_followups = await db.get_pending_followups()
                
                if not pending_followups:
                    return
                
                print(f"📋 Found {len(pending_followups)} pending follow-up(s)")
                
                for followup in pending_followups:
                    try:
                        await self.send_followup(db, followup)
                    except Exception as e:
                        print(f"❌ Error sending follow-up {followup.id}: {e}")
                
            except Exception as e:
                print(f"❌ Error checking follow-ups: {e}")
    
    async def send_followup(self, db: DBManager, followup: FollowUp):
        """Send a single follow-up message"""
        try:
            # Get lead
            lead = await db.get_lead_by_id(followup.lead_id)
            if not lead:
                print(f"⚠️ Lead {followup.lead_id} not found for follow-up {followup.id}")
                await db.update_followup_status(followup.id, 'cancelled')
                return
            
            print(f"📤 Sending {followup.followup_type} follow-up to {lead.name} via {followup.channel}")
            
            # Generate follow-up message
            message = await self.generate_followup_message(db, lead, followup)
            
            # Send via appropriate channel
            success = False
            if followup.channel == 'email':
                success = await self.send_email_followup(lead, message, followup)
            elif followup.channel == 'sms':
                success = await send_sms(lead.phone, message)
            elif followup.channel == 'whatsapp':
                success = await send_whatsapp(lead.phone, message)
            
            if success:
                # Update follow-up status
                await db.update_followup_status(followup.id, 'sent')
                
                # Save to conversations
                await db.add_conversation(
                    lead_id=lead.id,
                    message=message,
                    channel=followup.channel,
                    sender='ai',
                    metadata={'followup_id': followup.id, 'followup_type': followup.followup_type}
                )
                
                # Update lead
                lead.last_followup_at = datetime.now()
                lead.followup_count += 1
                await db.session.commit()
                
                print(f"✅ Follow-up sent successfully")
                
                # Schedule next follow-up if needed
                await self.schedule_next_followup(db, lead, followup)
            else:
                print(f"❌ Failed to send follow-up")
                await db.update_followup_status(followup.id, 'failed')
            
        except Exception as e:
            print(f"❌ Error sending follow-up: {e}")
            import traceback
            traceback.print_exc()
    
    async def generate_followup_message(
        self,
        db: DBManager,
        lead: Lead,
        followup: FollowUp
    ) -> str:
        """Generate personalized follow-up message using AI"""
        try:
            # Get conversation history
            conversations = await db.get_conversations_by_lead(lead.id, limit=5)
            
            # Build context
            context_builder = ContextBuilder(db)
            history_text = ""
            for conv in conversations[-3:]:  # Last 3 messages
                history_text += f"{conv.sender}: {conv.message[:100]}...\n"
            
            # Build prompt for LLM
            prompt = f"""Generate a friendly follow-up message for a customer.

Customer: {lead.name}
Status: {lead.lead_status}
Previous contacts: {lead.message_count}
Follow-up type: {followup.followup_type}
Channel: {followup.channel}

Recent conversation:
{history_text}

Generate a short, friendly follow-up message (2-3 sentences) that:
1. References previous conversation naturally
2. Offers help or next steps
3. Is appropriate for {followup.channel} channel

Message:"""
            
            # Generate with LLM
            response = self.llm.generate(prompt, max_tokens=150)
            
            # Clean response
            message = response.strip()
            
            # Fallback if generation fails
            if not message or len(message) < 10:
                message = self.get_default_followup_message(followup.followup_type)
            
            return message
            
        except Exception as e:
            print(f"❌ Error generating follow-up message: {e}")
            return self.get_default_followup_message(followup.followup_type)
    
    def get_default_followup_message(self, followup_type: str) -> str:
        """Get default follow-up message templates"""
        templates = {
            'reminder': "Hi! Just following up on our previous conversation. Do you have any questions I can help with?",
            'nurture': "Hi! I wanted to check in and see if you're still interested in learning more about our services.",
            'escalation': "Hi! I haven't heard back from you. Would you like to schedule a call with our team to discuss further?"
        }
        return templates.get(followup_type, templates['reminder'])
    
    async def send_email_followup(
        self,
        lead: Lead,
        message: str,
        followup: FollowUp
    ) -> bool:
        """Send follow-up via email"""
        subject = self.get_email_subject(followup.followup_type)
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <p>Hi {lead.name},</p>
            
            <p>{message}</p>
            
            <br>
            <p>Best regards,<br>
            <strong>TechCorp Team</strong></p>
            
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                Reply to this email if you have any questions.
            </p>
        </body>
        </html>
        """
        
        return await send_email(lead.email, subject, html_body)
    
    def get_email_subject(self, followup_type: str) -> str:
        """Get email subject based on follow-up type"""
        subjects = {
            'reminder': "Following up on our conversation",
            'nurture': "Just checking in",
            'escalation': "Would you like to discuss further?"
        }
        return subjects.get(followup_type, "Following up")
    
    async def schedule_next_followup(
        self,
        db: DBManager,
        lead: Lead,
        current_followup: FollowUp
    ):
        """Schedule next follow-up if needed"""
        try:
            # Check if max attempts reached
            if lead.followup_count >= self.max_attempts:
                print(f"⚠️ Max follow-up attempts reached for lead {lead.id}")
                return
            
            # Determine next follow-up channel and time
            next_channel = self.get_next_channel(current_followup.channel)
            next_time = self.get_next_followup_time(current_followup.channel)
            
            # Create next follow-up
            await db.create_followup(
                lead_id=lead.id,
                scheduled_time=next_time,
                followup_type='reminder',
                channel=next_channel
            )
            
            print(f"📅 Scheduled next follow-up for {next_time} via {next_channel}")
            
        except Exception as e:
            print(f"❌ Error scheduling next follow-up: {e}")
    
    def get_next_channel(self, current_channel: str) -> str:
        """Determine next channel for follow-up"""
        # Progression: email → sms → whatsapp
        channel_map = {
            'email': 'sms',
            'sms': 'whatsapp',
            'whatsapp': 'email'
        }
        return channel_map.get(current_channel, 'email')
    
    def get_next_followup_time(self, channel: str) -> datetime:
        """Calculate next follow-up time"""
        delays = {
            'email': self.email_delay,
            'sms': self.sms_delay,
            'whatsapp': self.sms_delay
        }
        delay_seconds = delays.get(channel, self.email_delay)
        return datetime.now() + timedelta(seconds=delay_seconds)
    
    async def create_followup_for_lead(
        self,
        lead_id: int,
        hours_delay: int = 24,
        followup_type: str = 'reminder',
        channel: str = None
    ):
        """Manually create a follow-up for a lead"""
        async with AsyncSessionLocal() as session:
            db = DBManager(session)
            
            try:
                lead = await db.get_lead_by_id(lead_id)
                if not lead:
                    print(f"⚠️ Lead {lead_id} not found")
                    return
                
                # Use preferred channel if not specified
                if not channel:
                    channel = lead.preferred_channel or 'email'
                
                scheduled_time = datetime.now() + timedelta(hours=hours_delay)
                
                followup = await db.create_followup(
                    lead_id=lead_id,
                    scheduled_time=scheduled_time,
                    followup_type=followup_type,
                    channel=channel
                )
                
                print(f"✅ Follow-up created: {followup.id} scheduled for {scheduled_time}")
                return followup
                
            except Exception as e:
                print(f"❌ Error creating follow-up: {e}")
                return None


# Singleton instance
follow_up_manager = FollowUpManager()