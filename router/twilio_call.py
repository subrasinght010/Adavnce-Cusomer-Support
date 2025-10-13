# router/twilio_call.py
"""
Twilio Voice Call Webhooks - Complete Implementation
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from database.crud import DBManager
from database.db import get_db
from services.phone_service import phone_service
from state.workflow_state import create_initial_state
from graph_workflows.workflow import workflow_router

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/voice/incoming")
async def incoming_call(request: Request, db: AsyncSession = Depends(get_db)):
    """Twilio incoming call webhook"""
    try:
        form = await request.form()
        from_number = form.get('From')
        call_sid = form.get('CallSid')
        
        logger.info(f"📞 Incoming: {from_number}")
        
        db_manager = DBManager(db)
        lead = await db_manager.get_or_create_lead(phone=from_number)
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna">Hello {lead.name or 'there'}! How can I help you today?</Say>
            <Gather input="speech" timeout="3" speechTimeout="auto" action="/webhook/twilio/voice/process" method="POST">
                <Say>Please tell me how I can assist you.</Say>
            </Gather>
            <Say>I didn't hear anything. Goodbye!</Say>
            <Hangup/>
        </Response>"""
        
        return Response(content=twiml, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Call error: {e}")
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Technical difficulties. Please try again.</Say>
            <Hangup/>
        </Response>"""
        return Response(content=twiml, media_type="application/xml")


@router.post("/voice/process")
async def process_speech(request: Request, db: AsyncSession = Depends(get_db)):
    """Process speech through workflow"""
    try:
        form = await request.form()
        speech = form.get('SpeechResult', '').strip()
        from_number = form.get('From')
        call_sid = form.get('CallSid')
        
        if not speech:
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>I didn't catch that. Could you repeat?</Say>
                <Gather input="speech" timeout="3" action="/webhook/twilio/voice/process"/>
            </Response>"""
            return Response(content=twiml, media_type="application/xml")
        
        logger.info(f"🎤 Speech from {from_number}: {speech}")
        
        db_manager = DBManager(db)
        lead = await db_manager.get_or_create_lead(phone=from_number)
        
        # Save conversation
        await db_manager.add_conversation(
            lead_id=lead.id,
            message=speech,
            channel="call",
            sender="user"
        )
        
        # Run through workflow
        state = create_initial_state(
            lead_id=str(lead.id),
            message=speech,
            channel="call",
            direction="inbound",
            lead_data={"phone": from_number, "name": lead.name}
        )
        
        result = await workflow_router.run(state)
        intelligence = result.get("intelligence_output", {})
        response_text = intelligence.get("response_text", "Thank you for calling.")
        
        # Save AI response
        await db_manager.add_conversation(
            lead_id=lead.id,
            message=response_text,
            channel="call",
            sender="ai"
        )
        
        # Check if needs to end call
        if intelligence.get("end_call", False):
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>{response_text}</Say>
                <Say>Thank you for calling. Goodbye!</Say>
                <Hangup/>
            </Response>"""
        else:
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>{response_text}</Say>
                <Gather input="speech" timeout="3" speechTimeout="auto" action="/webhook/twilio/voice/process">
                    <Say>Is there anything else I can help with?</Say>
                </Gather>
                <Say>Thank you for calling. Goodbye!</Say>
                <Hangup/>
            </Response>"""
        
        return Response(content=twiml, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Speech error: {e}")
        import traceback
        traceback.print_exc()
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Error processing request. Goodbye.</Say>
            <Hangup/>
        </Response>"""
        return Response(content=twiml, media_type="application/xml")


@router.post("/voice/twiml/{lead_id}")
@router.get("/voice/twiml/{lead_id}")
async def outgoing_twiml(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Generate TwiML for outgoing calls (scheduled callbacks)"""
    try:
        db_manager = DBManager(db)
        lead = await db_manager.get_lead(lead_id)
        
        if not lead:
            logger.error(f"Lead not found: {lead_id}")
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
            <Response><Hangup/></Response>"""
            return Response(content=twiml, media_type="application/xml")
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna">Hello {lead.name}, this is your scheduled callback.</Say>
            <Gather input="speech" timeout="3" action="/webhook/twilio/voice/process">
                <Say>How can I help you today?</Say>
            </Gather>
            <Say>Goodbye!</Say>
            <Hangup/>
        </Response>"""
        
        return Response(content=twiml, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"TwiML error: {e}")
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response><Hangup/></Response>"""
        return Response(content=twiml, media_type="application/xml")


@router.post("/voice/status/{lead_id}")
async def call_status(lead_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Track call status"""
    try:
        form = await request.form()
        status = form.get('CallStatus')
        call_sid = form.get('CallSid')
        duration = form.get('CallDuration', '0')
        
        logger.info(f"📞 Call {call_sid}: {status} ({duration}s)")
        
        if status == 'completed':
            db_manager = DBManager(db)
            await db_manager.update_lead(
                lead_id=lead_id,
                data={'last_contacted_at': datetime.utcnow()}
            )
            
            # Mark followup as completed if exists
            followups = await db_manager.get_pending_followups()
            for fu in followups:
                if str(fu.lead_id) == lead_id and fu.status == 'in_progress':
                    await db_manager.update_followup(
                        fu.id,
                        status='completed',
                        notes=f"Call completed: {duration}s"
                    )
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Status error: {e}")
        return {"status": "error"}


@router.post("/recording")
async def recording_callback(request: Request):
    """Handle call recording"""
    try:
        form = await request.form()
        recording_sid = form.get('RecordingSid')
        recording_url = form.get('RecordingUrl')
        call_sid = form.get('CallSid')
        duration = form.get('RecordingDuration', '0')
        
        logger.info(f"🎙️ Recording {recording_sid}: {duration}s")
        
        # TODO: Save recording URL to database
        # await db_manager.save_recording(call_sid, recording_url)
        
        return {"status": "ok", "recording_sid": recording_sid}
    
    except Exception as e:
        logger.error(f"Recording error: {e}")
        return {"status": "error"}