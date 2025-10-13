# main.py (CLEANED & OPTIMIZED - ALL BUGS FIXED)
import asyncio
import os
import json
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import jwt
import uvicorn

from fastapi import (
    FastAPI,
    Request,
    Form,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import (
    JSONResponse, 
    RedirectResponse, 
    HTMLResponse,
    Response  # ✅ Moved here from inside functions
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketState

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Project imports
from config.settings import settings as Settings
from database.crud import DBManager
from database.db import get_db, init_db
from database.models import User

from nodes.lead_manager_agent import lead_manager_agent
from utils.audio import (
    AudioValidator,
    check_silence_loop,
    handle_audio_chunk,
    handle_text_message,
    process_audio,
)
from utils.secure import verify_password, hash_password

from router.twilio_call import router as twilio_router

# Workers
from workers import worker_manager

# -------------------------
# Load env & constants
# -------------------------
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "access_token")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# -------------------------
# FastAPI app with lifespan
# -------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    print("\n" + "=" * 60)
    print("🚀 Application Starting...")
    print("=" * 60)
    
    try:
        await init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise

    lead_manager_task = asyncio.create_task(
        lead_manager_agent.start_continuous_operation()
    )
    
    print("✅ Lead Manager started (runs every 15 min)")
    
    yield
    

    try:
        await worker_manager.start_all_workers()
        print("✅ Background workers started")
    except Exception as e:
        print(f"⚠️  Warning: Some workers failed to start: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("✅ Application Ready!")
    print("=" * 60 + "\n")
    
    yield
        # SHUTDOWN
    lead_manager_task.cancel()
    print("✅ Shutdown lead manager")
    # Shutdown
    print("\n" + "=" * 60)
    print("🛑 Application Shutting Down...")
    print("=" * 60)
    
    try:
        await worker_manager.stop_all_workers()
        print("✅ Background workers stopped")
    except Exception as e:
        print(f"⚠️  Error stopping workers: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Application Shutdown Complete")
    print("=" * 60 + "\n")


app = FastAPI(title="Multi-Agent Communication System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# Include routers
app.include_router(twilio_router, prefix="/webhook/twilio")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Auth utilities
# -------------------------
def create_jwt_token(username: str, expires_hours: int = 1) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    payload = {"sub": username, "exp": exp}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        exp = payload.get("exp")
        if exp is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        if isinstance(exp, (int, float)):
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
        elif isinstance(exp, str):
            exp_datetime = datetime.fromisoformat(exp)
            if exp_datetime.tzinfo is None:
                exp_datetime = exp_datetime.replace(tzinfo=timezone.utc)
        else:
            exp_datetime = exp

        if datetime.now(timezone.utc) > exp_datetime:
            raise HTTPException(status_code=401, detail="Token has expired")

        return sub

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    try:
        return verify_jwt_token(token)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)


# -------------------------
# Routes (auth + pages)
# -------------------------
@app.get("/")
async def root(request: Request):
    """
    Root redirect logic:
    - Redirects to /voice if TTS is enabled
    - Redirects to /home if TTS is disabled
    """
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        verify_jwt_token(token)
    except HTTPException:
        print("❌ Invalid token, redirecting to login")
        return RedirectResponse(url="/login", status_code=303)
        
    try:
        if Settings.ENABLE_TTS in [False, "False", "false"]:
            print("⚠️  TTS is disabled, redirecting to home")
            return RedirectResponse(url="/home", status_code=303)
        else:
            print("✅ TTS is enabled, redirecting to voice chat")
            return RedirectResponse(url="/voice", status_code=303)
    except Exception as e:
        print(f"❌ Error checking TTS setting: {e}")
        return RedirectResponse(url="/login", status_code=303)


@app.get("/voice", response_class=HTMLResponse)
async def home_page(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(user, RedirectResponse):
        return user

    user_obj = await DBManager(session=db).get_user_by_username(username=user)
    if not user_obj:
        return HTMLResponse("User not found", status_code=404)

    return templates.TemplateResponse(
        "voice.html",
        {"request": request, "user_id": user_obj.id, "username": user_obj.username},
    )

@app.get("/home", response_class=HTMLResponse)
async def home_page(
    request: Request,
    user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(user, RedirectResponse):
        return user

    user_obj = await DBManager(session=db).get_user_by_username(username=user)
    if not user_obj:
        return HTMLResponse("User not found", status_code=404)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user_id": user_obj.id, "username": user_obj.username},
    )


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    result = await db.execute(select(User).where(User.username == username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(username=username, password=hash_password(password))
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return RedirectResponse(url="/login", status_code=303)


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        result = await db.execute(select(User).where(User.username == username))
        db_user = result.scalars().first()
        if db_user and verify_password(password, db_user.password):
            token = create_jwt_token(username)
            redirect_response = RedirectResponse(url="/", status_code=303)
            redirect_response.set_cookie(
                key="access_token", 
                value=token, 
                httponly=True, 
                secure=False, 
                samesite="Lax"
            )
            return redirect_response
    raise HTTPException(status_code=401, detail="Invalid credentials")


# -------------------------
# System Status Endpoints
# -------------------------
@app.get("/workers/status")
async def workers_status():
    """Get status of all background workers"""
    try:
        status = worker_manager.get_all_status()
        return {
            "status": "ok",
            "workers": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Multi-Agent Communication System"
    }


# -------------------------
# SMS Webhook
# -------------------------
@app.post("/webhook/sms")
async def webhook_sms(request: Request):
    """
    Twilio SMS webhook endpoint
    Configure in Twilio Console: https://yourserver.com/webhook/sms
    """
    try:
        form_data = await request.form()
        webhook_data = {
            'From': form_data.get('From'),
            'To': form_data.get('To'),
            'Body': form_data.get('Body'),
            'MessageSid': form_data.get('MessageSid')
        }
        
        print(f"📱 SMS Webhook received: {webhook_data}")
        
        # Process SMS
        result = await sms_handler.handle_incoming_sms(webhook_data)
        
        # Return TwiML response (required by Twilio)
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )
        
    except Exception as e:
        print(f"❌ SMS webhook error: {e}")
        import traceback
        traceback.print_exc()
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
            status_code=200
        )


# -------------------------
# WhatsApp Webhook
# -------------------------
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Twilio WhatsApp webhook endpoint
    Configure in Twilio Console: https://yourserver.com/webhook/whatsapp
    """
    try:
        form_data = await request.form()
        webhook_data = {
            'From': form_data.get('From'),
            'To': form_data.get('To'),
            'Body': form_data.get('Body'),
            'MessageSid': form_data.get('MessageSid'),
            'MediaUrl0': form_data.get('MediaUrl0'),
            'NumMedia': form_data.get('NumMedia', '0')
        }
        
        print(f"💬 WhatsApp Webhook received: {webhook_data}")
        
        # Process WhatsApp
        result = await whatsapp_handler.handle_incoming_whatsapp(webhook_data)
        
        # Return TwiML response
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )
        
    except Exception as e:
        print(f"❌ WhatsApp webhook error: {e}")
        import traceback
        traceback.print_exc()
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
            status_code=200
        )


# -------------------------
# Webhook Status Check
# -------------------------
@app.get("/webhook/status")
async def webhook_status():
    """Check if webhooks are working"""
    return {
        "status": "online",
        "endpoints": {
            "sms": "/webhook/sms",
            "whatsapp": "/webhook/whatsapp",
            "twilio_voice": "/webhook/twilio/voice/*"
        },
        "timestamp": datetime.now().isoformat()
    }


# -------------------------
# WebSocket Helper
# -------------------------
async def safe_send(websocket: WebSocket, data: dict) -> bool:
    """Safely send JSON data to WebSocket"""
    try:
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.send_json(data)
            return True
    except Exception as e:
        print(f"Send failed: {e}")
    return False


@app.websocket("/voice_chat")
async def voice_chat(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """WebSocket endpoint for real-time voice communication with conversation display"""
    
    await websocket.accept()
    print("✅ WebSocket connected")
    print("Client-side VAD handles speech detection, server validates quality")

    # Initialize state
    validator = AudioValidator()
    lead_id_ref = {'value': None}
    audio_data_ref = {'value': b''}
    last_chunk_time_ref = {'value': datetime.now()}
    is_receiving_ref = {'value': False}
    silence_check_task = None

    try:
        # Start silence checker background task
        silence_check_task = asyncio.create_task(
            check_silence_loop(
                audio_data_ref,
                last_chunk_time_ref,
                is_receiving_ref,
                websocket,
                validator,
                safe_send
            )
        )
        
        # Main message loop
        while True:
            if websocket.application_state != WebSocketState.CONNECTED:
                break
            
            try:
                # Receive message (can be binary audio or JSON control)
                message = await websocket.receive()
                
                # Handle different message types
                if "bytes" in message:
                    # Binary audio data
                    chunk = message["bytes"]
                    await handle_audio_chunk(
                        chunk,
                        audio_data_ref,
                        is_receiving_ref,
                        last_chunk_time_ref,
                        websocket,
                        validator,
                        safe_send  # Add this parameter
                    )
                
                elif "text" in message:
                    # JSON control messages
                    data = json.loads(message["text"])
                    should_break = await handle_text_message(
                        data,
                        lead_id_ref,
                        is_receiving_ref,
                        last_chunk_time_ref,
                        audio_data_ref,
                        websocket,
                        validator,
                        safe_send  # Add this parameter
                    )
                    
                    if should_break:
                        break
            
            except WebSocketDisconnect:
                print("🔌 Client disconnected")
                break
            except Exception as e:
                print(f"Error processing message: {e}")
                break
    
    except Exception as e:
        print(f"Unexpected error in voice_chat: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if silence_check_task and not silence_check_task.done():
            silence_check_task.cancel()
            try:
                await silence_check_task
            except asyncio.CancelledError:
                pass
        
        # Process remaining audio
        if audio_data_ref.get('value'):
            print("Processing remaining audio buffer...")
            try:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await process_audio(
                        audio_data_ref['value'],
                        websocket,
                        validator,
                        safe_send
                    )
            except Exception as e:
                print(f"Failed to process remaining audio: {e}")
        
        # Print session statistics
        final_stats = validator.get_stats()
        print("=" * 50)
        print("Session Statistics:")
        print(f"  Total Chunks: {final_stats.get('total_received', 0)}")
        print(f"  Valid Chunks: {final_stats.get('total_valid', 0)}")
        print(f"  Total Data: {final_stats.get('total_bytes', 0) / 1024:.2f} KB")
        print(f"  Validation Rate: {final_stats.get('validation_rate', 0)*100:.1f}%")
        if 'avg_rms' in final_stats:
            print(f"  Avg RMS: {final_stats.get('avg_rms', 0):.3f}")
        print("=" * 50)
        
        # Close database session
        if db:
            try:
                await db.close()
            except Exception as e:
                print(f"Error closing database: {e}")
        
        # Close WebSocket
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
                print("WebSocket closed cleanly")
            except Exception as e:
                print(f"Error closing WebSocket: {e}")

# -------------------------
# Main entry
# -------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
