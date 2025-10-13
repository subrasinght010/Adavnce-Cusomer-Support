# router/webhook.py
"""
Webhook Routes - Unified handlers routing directly to workflows
Replaces: email_monitor, sms_handler, whatsapp_handler
"""

from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
import logging

from database.db import get_db
from database.crud import DBManager
from state.workflow_state import create_initial_state
from graph_workflows.workflow import workflow_router

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# SMS WEBHOOK (Twilio)
# ============================================================================

@router.post("/webhook/sms")
async def sms_webhook(request: Request):
    """Handle incoming SMS from Twilio"""
    
    try:
        form_data = await request.form()
        from_number = form_data.get("From")
        message_body = form_data.get("Body")
        message_sid = form_data.get("MessageSid")
        
        logger.info(f"📱 SMS from {from_number}: {message_body}")
        
        # Get or create lead
        async with get_db() as db:
            db_manager = DBManager(db)
            lead = await db_manager.get_or_create_lead(
                phone=from_number,
                channel="sms"
            )
            
            # Save incoming message
            await db_manager.create_conversation({
                "lead_id": lead.id,
                "message": message_body,
                "direction": "inbound",
                "channel": "sms",
                "metadata": {"message_sid": message_sid}
            })
            
            # Create workflow state
            state = create_initial_state(
                lead_id=str(lead.id),
                message=message_body,
                channel="sms",
                direction="inbound",
                lead_data={
                    "phone": from_number,
                    "name": lead.name or from_number
                }
            )
            
            # Run through workflow (Intelligence → Message Format → Send)
            result = await workflow_router.run(state)
            
            # Get formatted response
            intelligence = result.get("intelligence_output", {})
            response_text = intelligence.get("response_text", "Thank you for your message.")
            
            # Return TwiML response
            resp = MessagingResponse()
            resp.message(response_text)
            return Response(content=str(resp), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"SMS webhook error: {e}")
        resp = MessagingResponse()
        resp.message("We're experiencing technical difficulties. Please try again.")
        return Response(content=str(resp), media_type="application/xml")


# ============================================================================
# WHATSAPP WEBHOOK (Twilio)
# ============================================================================

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp from Twilio"""
    
    try:
        form_data = await request.form()
        from_number = form_data.get("From").replace("whatsapp:", "")
        message_body = form_data.get("Body")
        message_sid = form_data.get("MessageSid")
        media_url = form_data.get("MediaUrl0")  # If image/file attached
        
        logger.info(f"💬 WhatsApp from {from_number}: {message_body}")
        
        async with get_db() as db:
            db_manager = DBManager(db)
            lead = await db_manager.get_or_create_lead(
                phone=from_number,
                channel="whatsapp"
            )
            
            # Save incoming message
            await db_manager.create_conversation({
                "lead_id": lead.id,
                "message": message_body,
                "direction": "inbound",
                "channel": "whatsapp",
                "metadata": {
                    "message_sid": message_sid,
                    "media_url": media_url
                }
            })
            
            state = create_initial_state(
                lead_id=str(lead.id),
                message=message_body,
                channel="whatsapp",
                direction="inbound",
                lead_data={
                    "phone": from_number,
                    "name": lead.name or from_number
                }
            )
            
            result = await workflow_router.run(state)
            intelligence = result.get("intelligence_output", {})
            response_text = intelligence.get("response_text", "Thank you!")
            
            resp = MessagingResponse()
            resp.message(response_text)
            return Response(content=str(resp), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        resp = MessagingResponse()
        resp.message("Error processing your message. Please try again.")
        return Response(content=str(resp), media_type="application/xml")


# ============================================================================
# EMAIL WEBHOOK (SendGrid/IMAP - if using webhooks)
# ============================================================================

@router.post("/webhook/email")
async def email_webhook(request: Request):
    """
    Handle incoming email webhook (from SendGrid Inbound Parse)
    Alternative: Use IMAP polling in background worker
    """
    
    try:
        data = await request.json()
        from_email = data.get("from")
        subject = data.get("subject")
        body = data.get("text") or data.get("html")
        
        logger.info(f"📧 Email from {from_email}: {subject}")
        
        async with get_db() as db:
            db_manager = DBManager(db)
            lead = await db_manager.get_or_create_lead(
                email=from_email,
                channel="email"
            )
            
            await db_manager.create_conversation({
                "lead_id": lead.id,
                "message": f"Subject: {subject}\n\n{body}",
                "direction": "inbound",
                "channel": "email",
                "metadata": {"subject": subject}
            })
            
            state = create_initial_state(
                lead_id=str(lead.id),
                message=body,
                channel="email",
                direction="inbound",
                lead_data={
                    "email": from_email,
                    "name": lead.name or from_email
                }
            )
            
            result = await workflow_router.run(state)
            
            # Email responses handled by communication agent
            # No immediate response needed for webhook
            return {"status": "processed"}
    
    except Exception as e:
        logger.error(f"Email webhook error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# DELIVERY STATUS WEBHOOKS
# ============================================================================

@router.post("/webhook/sms-status")
async def sms_status_webhook(request: Request):
    """Track SMS delivery status from Twilio"""
    
    try:
        form_data = await request.form()
        message_sid = form_data.get("MessageSid")
        status = form_data.get("MessageStatus")  # delivered, failed, etc.
        
        async with get_db() as db:
            db_manager = DBManager(db)
            
            # Find conversation by message_sid
            conv = await db_manager.get_conversation_by_metadata("message_sid", message_sid)
            if conv:
                await db_manager.update_conversation(
                    conv.id,
                    {"delivery_status": status}
                )
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"SMS status webhook error: {e}")
        return {"status": "error"}


@router.post("/webhook/email-status")
async def email_status_webhook(request: Request):
    """Track email events from SendGrid (opens, clicks, bounces)"""
    
    try:
        events = await request.json()
        
        for event in events:
            event_type = event.get("event")  # delivered, open, click, bounce
            message_id = event.get("sg_message_id")
            
            # Update conversation delivery status
            async with get_db() as db:
                db_manager = DBManager(db)
                conv = await db_manager.get_conversation_by_metadata("message_id", message_id)
                if conv:
                    await db_manager.update_conversation(
                        conv.id,
                        {"delivery_status": event_type}
                    )
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Email status webhook error: {e}")
        return {"status": "error"}