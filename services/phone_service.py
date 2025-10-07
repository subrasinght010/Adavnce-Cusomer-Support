# services/phone_service.py
"""
Phone Service - Twilio Voice API
Handles outgoing and incoming voice calls
"""

import os
import logging
from typing import Dict, Optional
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Say

logger = logging.getLogger(__name__)

# Initialize Twilio client
twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)


class PhoneService:
    """
    Handles Twilio voice calls (incoming and outgoing)
    """
    
    def __init__(self):
        self.twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        self.base_url = os.getenv("BASE_URL", "https://yourdomain.com")
    
    async def initiate_call(
        self,
        to_number: str,
        lead_id: str,
        callback_url: str = None
    ) -> Dict:
        """
        Initiate outgoing call
        
        Args:
            to_number: Phone number to call (E.164 format: +91XXXXXXXXXX)
            lead_id: Lead identifier
            callback_url: Webhook URL for call events
        
        Returns:
            {
                "success": bool,
                "call_sid": str,
                "status": str,
                "error": str (if failed)
            }
        """
        try:
            if not callback_url:
                callback_url = f"{self.base_url}/webhook/twilio/voice/{lead_id}"
            
            # Create TwiML for initial greeting
            twiml_url = f"{self.base_url}/webhook/twilio/voice/twiml/{lead_id}"
            
            logger.info(f"📞 Initiating call to {to_number}")
            
            call = twilio_client.calls.create(
                to=to_number,
                from_=self.twilio_phone,
                url=twiml_url,  # TwiML instructions for call
                status_callback=callback_url,  # Status updates
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                status_callback_method='POST',
                record=True,  # Record the call
                recording_status_callback=f"{self.base_url}/webhook/twilio/recording",
                timeout=30,  # Ring for 30 seconds
                machine_detection='Enable',  # Detect answering machines
            )
            
            logger.info(f"✅ Call initiated: {call.sid}")
            
            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "to": to_number
            }
        
        except Exception as e:
            logger.error(f"❌ Call initiation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_greeting_twiml(
        self,
        lead_name: str = None,
        initial_message: str = None
    ) -> str:
        """
        Generate TwiML for initial call greeting
        
        This TwiML:
        1. Greets the user
        2. Gathers their speech input
        3. Sends speech to our webhook for processing
        """
        response = VoiceResponse()
        
        # Initial greeting
        if initial_message:
            greeting = initial_message
        elif lead_name:
            greeting = f"Hello {lead_name}, this is your scheduled callback. How can I help you today?"
        else:
            greeting = "Hello! How can I help you today?"
        
        response.say(greeting, voice='Polly.Joanna', language='en-US')
        
        # Gather speech input
        gather = Gather(
            input='speech',
            action='/webhook/twilio/voice/process',
            method='POST',
            speech_timeout='auto',
            language='en-US',
            enhanced=True  # Enhanced speech recognition
        )
        
        gather.say(
            "I'm listening...",
            voice='Polly.Joanna',
            language='en-US'
        )
        
        response.append(gather)
        
        # If no input, prompt again
        response.say(
            "I didn't catch that. Could you please repeat?",
            voice='Polly.Joanna',
            language='en-US'
        )
        response.redirect('/webhook/twilio/voice/twiml')
        
        return str(response)
    
    def generate_response_twiml(
        self,
        message: str,
        continue_listening: bool = True
    ) -> str:
        """
        Generate TwiML for AI response during call
        
        Args:
            message: AI response text
            continue_listening: Whether to gather more input
        """
        response = VoiceResponse()
        
        # Speak AI response
        response.say(message, voice='Polly.Joanna', language='en-US')
        
        if continue_listening:
            # Gather next input
            gather = Gather(
                input='speech',
                action='/webhook/twilio/voice/process',
                method='POST',
                speech_timeout='auto',
                language='en-US',
                enhanced=True
            )
            response.append(gather)
            
            # Timeout handling
            response.say("Are you still there?", voice='Polly.Joanna')
            response.redirect('/webhook/twilio/voice/twiml')
        else:
            # End call
            response.say("Thank you for calling. Goodbye!", voice='Polly.Joanna')
            response.hangup()
        
        return str(response)
    
    def generate_hangup_twiml(self) -> str:
        """Generate TwiML to end call"""
        response = VoiceResponse()
        response.say("Thank you! Have a great day.", voice='Polly.Joanna')
        response.hangup()
        return str(response)
    
    async def get_call_status(self, call_sid: str) -> Dict:
        """
        Get current status of a call
        
        Returns:
            {
                "status": "queued|ringing|in-progress|completed|busy|failed|no-answer",
                "duration": int (seconds),
                "direction": "inbound|outbound",
                "from": "+91XXX",
                "to": "+91XXX"
            }
        """
        try:
            call = twilio_client.calls(call_sid).fetch()
            
            return {
                "status": call.status,
                "duration": call.duration,
                "direction": call.direction,
                "from": call.from_,
                "to": call.to,
                "price": call.price,
                "price_unit": call.price_unit
            }
        
        except Exception as e:
            logger.error(f"Failed to get call status: {e}")
            return {"status": "unknown", "error": str(e)}
    
    async def end_call(self, call_sid: str) -> bool:
        """
        Forcefully end an ongoing call
        """
        try:
            call = twilio_client.calls(call_sid).update(status='completed')
            logger.info(f"✅ Call {call_sid} ended")
            return True
        except Exception as e:
            logger.error(f"Failed to end call: {e}")
            return False


# Global instance
phone_service = PhoneService()