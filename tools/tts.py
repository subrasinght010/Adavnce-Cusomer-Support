# tools/tts.py
"""
Text-to-Speech service with conditional enabling
"""

import asyncio
from typing import Optional
import base64
from config.settings import settings

# Import TTS providers only if TTS is enabled
if settings.ENABLE_TTS:
    if settings.TTS_PROVIDER == "openai":
        from openai import AsyncOpenAI
        openai_client = AsyncOpenAI()
    elif settings.TTS_PROVIDER == "elevenlabs":
        # Import ElevenLabs SDK if you're using it
        pass
    elif settings.TTS_PROVIDER == "google":
        # Import Google TTS if you're using it
        pass


async def generate_speech(text: str) -> Optional[dict]:
    """
    Convert text to speech (only if ENABLE_TTS is true)
    
    Args:
        text: Text to convert
    
    Returns:
        Dictionary with audio data and metadata, or None if TTS disabled
    """
    
    # If TTS is disabled, return None
    if not settings.ENABLE_TTS:
        return None
    
    try:
        if settings.TTS_PROVIDER == "openai":
            return await _generate_openai_tts(text)
        elif settings.TTS_PROVIDER == "elevenlabs":
            return await _generate_elevenlabs_tts(text)
        elif settings.TTS_PROVIDER == "google":
            return await _generate_google_tts(text)
        else:
            print(f"⚠️ Unknown TTS provider: {settings.TTS_PROVIDER}")
            return None
            
    except Exception as e:
        print(f"❌ TTS generation error: {e}")
        return None


async def _generate_openai_tts(text: str) -> Optional[dict]:
    """Generate speech using OpenAI TTS"""
    try:
        response = await openai_client.audio.speech.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.TTS_VOICE,
            input=text,
            response_format="mp3"
        )
        
        # Get audio bytes
        audio_bytes = response.content
        
        # Convert to base64 for WebSocket transmission
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        return {
            "audio_data": audio_base64,
            "format": "mp3",
            "provider": "openai",
            "voice": settings.TTS_VOICE
        }
        
    except Exception as e:
        print(f"OpenAI TTS Error: {e}")
        return None


async def _generate_elevenlabs_tts(text: str) -> Optional[dict]:
    """Generate speech using ElevenLabs"""
    # Implement if using ElevenLabs
    print("⚠️ ElevenLabs TTS not yet implemented")
    return None


async def _generate_google_tts(text: str) -> Optional[dict]:
    """Generate speech using Google TTS"""
    # Implement if using Google TTS
    print("⚠️ Google TTS not yet implemented")
    return None


# Utility function to check if TTS is enabled
def is_tts_enabled() -> bool:
    """Check if TTS is enabled"""
    return settings.ENABLE_TTS