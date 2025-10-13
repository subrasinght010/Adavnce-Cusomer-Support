# main.py - ADD THESE TWILIO VOICE WEBHOOKS

"""
Add these endpoints to your existing main.py
These handle Twilio voice calls (both incoming and outgoing)
"""

from datetime import datetime
import logging

from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import DBManager
from database.db import get_db
from services.phone_service import phone_service
from graph_workflows.workflow import workflow_router as workflow_runner

# Create router
router = APIRouter()
logger = logging.getLogger(__name__)
# ============================================================================
# TWILIO VOICE WEBHOOKS - INCOMING CALLS
# ============================================================================

@router.post("/webhook/twilio/voice/incoming")
async def twilio_incoming_call(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Twilio webhook for INCOMING calls
    
    When someone calls your Twilio number, this endpoint is triggered
    
    Configure in Twilio Console:
    Voice & Fax → Phone Numbers → Your Number → Voice Configuration
    A CALL COMES IN: Webhook → https://yourdomain.com/webhook/twilio/voice/incoming
    """
    try:
        form_data = await request.form()
        
        from_number = form_data.get('From', '').strip()
        to_number = form_data.get('To', '').strip()
        call_sid = form_data.get('CallSid', '')
        call_status = form_data.get('CallStatus', '')
        
        logger.info(f"📞 Incoming call from {from_number} - Status: {call_status}")
        
        # Find or create lead
        db_manager = DBManager(db)
        lead = await db_manager.get_or_create_lead(
            phone=from_number,
            name=f"Caller {from_number[-4:]}"
        )
        
        logger.info(f"✅ Lead identified: {lead.id}")
        
        # Generate initial greeting TwiML
        twiml = phone_service.generate_greeting_twiml(
            lead_name=lead.name,
            initial_message="Hello! Thank you for calling. How can I help you today?"
        )
        
        return FastAPIResponse(
            content=twiml,
            media_type="application/xml"
        )
    
    except Exception as e:
        logger.error(f"❌ Incoming call error: {e}")
        
        # Return error TwiML
        error_twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna">Sorry, we're experiencing technical difficulties. Please try again later.</Say>
            <Hangup/>
        </Response>"""
        
        return FastAPIResponse(
            content=error_twiml,
            media_type="application/xml"
        )


# ============================================================================
# TWILIO VOICE WEBHOOKS - SPEECH PROCESSING
# ============================================================================

@router.post("/webhook/twilio/voice/process")
async def twilio_process_speech(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Process speech input from Twilio call
    
    CRITICAL: This is where speech goes through FULL WORKFLOW
    
    Flow:
    1. Get transcribed speech from Twilio
    2. Find lead by phone number
    3. Run through COMPLETE optimized workflow
    4. Return TwiML with AI response
    """
    try:
        form_data = await request.form()
        
        speech_result = form_data.get('SpeechResult', '').strip()
        from_number = form_data.get('From', '').strip()
        call_sid = form_data.get('CallSid', '')
        confidence = form_data.get('Confidence', '0')
        
        if not speech_result:
            # No speech detected
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="Polly.Joanna">I didn't catch that. Could you please repeat?</Say>
                <Redirect>/webhook/twilio/voice/incoming</Redirect>
            </Response>"""
            return FastAPIResponse(content=twiml, media_type="application/xml")
        
        logger.info(f"🎤 Speech from {from_number}: {speech_result} (confidence: {confidence})")
        
        # Find lead
        db_manager = DBManager(db)
        lead = await db_manager.get_or_create_lead(phone=from_number)
        
        # CRITICAL: Run through COMPLETE OPTIMIZED WORKFLOW
        # This will:
        # - Detect intent
        # - Query knowledge base
        # - Possibly send email/SMS during call
        # - Possibly schedule callback
        # - Update database
        # - Generate response
        
        result = await workflow_runner.run(
            lead_id=lead.id,
            message=speech_result,
            channel="twilio_call",
            lead_data={
                "name": lead.name,
                "phone": lead.phone,
                "email": lead.email,
                "call_sid": call_sid,
                "context": "ongoing_twilio_call"
            }
        )
        
        # Get AI response
        ai_response = result.get("final_response", "I understand. How else can I help?")
        
        # Check if conversation should end
        intent = result.get("detected_intent", "")
        should_continue = intent not in ["end_conversation", "goodbye"]
        
        # Log any actions taken
        if result.get("communication_sent"):
            logger.info(f"   📧 Email/SMS sent during call to {lead.email or lead.phone}")
        
        if result.get("callback_scheduled"):
            logger.info(f"   📅 New callback scheduled during call")
        
        # Generate response TwiML
        twiml = phone_service.generate_response_twiml(
            message=ai_response,
            continue_listening=should_continue
        )
        
        return FastAPIResponse(
            content=twiml,
            media_type="application/xml"
        )
    
    except Exception as e:
        logger.error(f"❌ Speech processing error: {e}")
        
        error_twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna">I'm sorry, I encountered an error. Let me transfer you to a specialist.</Say>
            <Hangup/>
        </Response>"""
        
        return FastAPIResponse(
            content=error_twiml,
            media_type="application/xml"
        )


# ============================================================================
# TWILIO VOICE WEBHOOKS - OUTGOING CALLS (TwiML)
# ============================================================================

@router.post("/webhook/twilio/voice/twiml/{lead_id}")
@router.get("/webhook/twilio/voice/twiml/{lead_id}")
async def twilio_outgoing_twiml(
    lead_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate TwiML for OUTGOING calls (scheduled callbacks)
    
    Called by Execute Call Worker when initiating outgoing calls
    """
    try:
        # Get lead data
        db_manager = DBManager(db)
        lead = await db_manager.get_lead(lead_id)
        
        if not lead:
            logger.error(f"Lead not found: {lead_id}")
            twiml = phone_service.generate_hangup_twiml()
            return FastAPIResponse(content=twiml, media_type="application/xml")
        
        # Generate greeting TwiML
        twiml = phone_service.generate_greeting_twiml(
            lead_name=lead.name,
            initial_message=f"Hello {lead.name}, this is your scheduled callback. How can I help you today?"
        )
        
        return FastAPIResponse(
            content=twiml,
            media_type="application/xml"
        )
    
    except Exception as e:
        logger.error(f"❌ TwiML generation error: {e}")
        twiml = phone_service.generate_hangup_twiml()
        return FastAPIResponse(content=twiml, media_type="application/xml")


# ============================================================================
# TWILIO VOICE WEBHOOKS - CALL STATUS
# ============================================================================

@router.post("/webhook/twilio/voice/{lead_id}")
async def twilio_call_status(
    lead_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Call status webhook - tracks call progress
    
    Receives updates when call status changes:
    - initiated
    - ringing
    - answered (in-progress)
    - completed
    """
    try:
        form_data = await request.form()
        
        call_sid = form_data.get('CallSid', '')
        call_status = form_data.get('CallStatus', '')
        call_duration = form_data.get('CallDuration', '0')
        
        logger.info(f"📞 Call status for {lead_id}: {call_status} (SID: {call_sid})")
        
        db_manager = DBManager(db)
        
        # Update lead's last contact
        if call_status in ['in-progress', 'completed']:
            await db_manager.update_lead(
                lead_id=lead_id,
                last_contacted_at=datetime.utcnow()
            )
        
        # If call completed, mark any associated followup as completed
        if call_status == 'completed':
            # Find followup for this call
            followups = await db_manager.get_pending_followups()
            for followup in followups:
                if followup.lead_id == lead_id and followup.status == 'in_progress':
                    await db_manager.update_followup(
                        followup.id,
                        status='completed',
                        notes=f"Call completed. Duration: {call_duration}s. SID: {call_sid}"
                    )
                    break
        
        return {"status": "ok", "call_status": call_status}
    
    except Exception as e:
        logger.error(f"❌ Call status error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# TWILIO VOICE WEBHOOKS - RECORDING
# ============================================================================

@router.post("/webhook/twilio/recording")
async def twilio_recording_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Recording callback - saves call recording URL
    """
    try:
        form_data = await request.form()
        
        recording_sid = form_data.get('RecordingSid', '')
        recording_url = form_data.get('RecordingUrl', '')
        call_sid = form_data.get('CallSid', '')
        recording_duration = form_data.get('RecordingDuration', '0')
        
        logger.info(f"🎙️ Recording available: {recording_sid} ({recording_duration}s)")
        
        # Save recording URL to database (add this field to your models if needed)
        # await db_manager.save_recording(call_sid, recording_url)
        
        return {"status": "ok", "recording_sid": recording_sid}
    
    except Exception as e:
        logger.error(f"❌ Recording callback error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# TEST ENDPOINT - Make Outgoing Call
# ============================================================================

@router.post("/api/test/make-call")
async def test_make_call(
    phone: str,
    lead_id: str = None,
    message: str = None
):
    """
    Test endpoint to manually trigger outgoing call
    
    Usage:
    POST /api/test/make-call
    {
        "phone": "+919876543210",
        "lead_id": "lead_123",
        "message": "Hello, this is a test call"
    }
    """
    try:
        if not lead_id:
            lead_id = f"test_{phone[-4:]}"
        
        result = await phone_service.initiate_call(
            to_number=phone,
            lead_id=lead_id,
            callback_url=f"/webhook/twilio/voice/{lead_id}"
        )
        
        return {
            "status": "success" if result.get("success") else "failed",
            "result": result
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }