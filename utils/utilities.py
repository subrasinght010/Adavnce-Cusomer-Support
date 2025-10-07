import asyncio
from datetime import datetime
from fastapi.websockets import WebSocketState
import jwt
from fastapi import HTTPException
from typing import Optional, Dict, Any
from fastapi import WebSocket
from starlette.websockets import WebSocketState
import soundfile as sf
import numpy as np
from collections import deque

from tools.stt import transcribe_with_faster_whisper
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"

# Configuration
SILENCE_TIMEOUT = 1.2  # seconds - optimized for VAD
MAX_AUDIO_DURATION = 30  # seconds
MIN_AUDIO_DURATION = 0.2  # seconds - minimum 200ms
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 4  # Changed from 2 to 4 (Float32 = 4 bytes per sample)
MIN_ENERGY_THRESHOLD = 0.001  # Minimum energy to not be complete silence
CHUNK_VALIDATION_WINDOW = 10  # Keep last N chunks for validation



def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, stored_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
    except ValueError:
        print("❌ Error: Stored password is not a valid bcrypt hash.")
        return False



# -------------------------
# Audio helpers
# -------------------------
def save_float32_to_wav(float32_data: bytes, filename: str = "received_audio.wav", sample_rate: int = 16000) -> None:
    """
    Save Float32 audio bytes to a WAV file at the specified sample rate.
    Saves as Float32 format (no conversion to Int16).
    """
    # Convert bytes to float32 array
    audio_array = np.frombuffer(float32_data, dtype=np.float32)
    
    # Save directly as Float32 WAV
    sf.write(filename, audio_array, sample_rate, subtype='FLOAT')


class AudioValidator:
    """Validates audio data for technical quality (not speech detection)"""
    
    def __init__(self):
        self.recent_chunks = deque(maxlen=CHUNK_VALIDATION_WINDOW)
        self.total_received = 0
        self.total_valid = 0
        self.total_bytes = 0
        
    def validate_chunk(self, chunk: bytes) -> bool:
        """Validate audio chunk for technical correctness (Float32 format)"""
        self.total_received += 1
        
        if len(chunk) == 0:
            return False
            
        # Must be 32-bit (4 bytes) aligned for Float32
        if len(chunk) % 4 != 0:
            print(f"⚠️ Chunk not 32-bit aligned: {len(chunk)} bytes")
            return False
        
        # Convert to numpy array for analysis
        try:
            audio_array = np.frombuffer(chunk, dtype=np.float32)
        except Exception as e:
            print(f"⚠️ Failed to convert chunk to array: {e}")
            return False
        
        # Check for all zeros (dead audio) - this is a technical issue, not VAD
        if np.all(audio_array == 0):
            # Silent chunks are technically valid, just log occasionally
            if self.total_received % 100 == 0:
                print("ℹ️ Receiving silent audio chunks")
            return True  # Still valid, just silent
        
        # Check for values outside valid Float32 range (-1.0 to 1.0)
        invalid_samples = np.sum((audio_array < -1.0) | (audio_array > 1.0))
        if invalid_samples > 0:
            invalid_rate = invalid_samples / len(audio_array)
            print(f"⚠️ Invalid Float32 values detected: {invalid_rate*100:.1f}% out of range")
        
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_array ** 2))
        
        # Get peak amplitude
        max_val = np.max(np.abs(audio_array))
        
        # Store chunk info
        self.recent_chunks.append({
            'size': len(chunk),
            'rms': rms,
            'max': max_val,
            'invalid_rate': invalid_samples / len(audio_array) if len(audio_array) > 0 else 0
        })
        
        self.total_valid += 1
        self.total_bytes += len(chunk)
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        if not self.recent_chunks:
            return {
                'total_received': self.total_received,
                'total_valid': self.total_valid,
                'total_bytes': self.total_bytes
            }
        
        avg_rms = np.mean([c['rms'] for c in self.recent_chunks])
        avg_size = np.mean([c['size'] for c in self.recent_chunks])
        avg_invalid = np.mean([c['invalid_rate'] for c in self.recent_chunks])
        
        return {
            'total_received': self.total_received,
            'total_valid': self.total_valid,
            'total_bytes': self.total_bytes,
            'avg_rms': float(avg_rms),
            'avg_chunk_size': float(avg_size),
            'avg_invalid_rate': float(avg_invalid),
            'validation_rate': self.total_valid / max(self.total_received, 1)
        }


async def analyze_audio_quality(audio_bytes: bytes) -> Dict[str, Any]:
    """Analyze audio technical quality (NOT speech detection - client VAD handles that)"""
    try:
        # Convert Float32 bytes to array
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Calculate technical metrics
        rms_energy = np.sqrt(np.mean(audio_array ** 2))
        peak_amplitude = np.max(np.abs(audio_array))
        duration = len(audio_array) / SAMPLE_RATE
        
        # Check for completely silent audio (technical issue)
        is_completely_silent = rms_energy < MIN_ENERGY_THRESHOLD
        
        # Check for out-of-range values
        invalid_samples = np.sum((audio_array < -1.0) | (audio_array > 1.0))
        invalid_rate = invalid_samples / len(audio_array) if len(audio_array) > 0 else 0
        has_invalid_values = invalid_rate > 0.01  # More than 1% invalid
        
        # Calculate dynamic range
        dynamic_range_db = 20 * np.log10(peak_amplitude / (rms_energy + 1e-10))
        
        return {
            'duration': duration,
            'rms_energy': float(rms_energy),
            'peak_amplitude': float(peak_amplitude),
            'invalid_rate': float(invalid_rate),
            'dynamic_range_db': float(dynamic_range_db),
            'is_completely_silent': is_completely_silent,
            'has_invalid_values': has_invalid_values,
            'is_technically_valid': not (is_completely_silent or has_invalid_values)
        }
    except Exception as e:
        print(f"❌ Audio analysis failed: {e}")
        return {'is_technically_valid': True}  # Default to processing


async def preprocess_audio(audio_bytes: bytes) -> bytes:
    """Preprocess Float32 audio to improve quality"""
    try:
        # Convert Float32 bytes to array
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Remove DC offset
        audio_array = audio_array - np.mean(audio_array)
        
        # Clip to valid range
        audio_array = np.clip(audio_array, -1.0, 1.0)
        
        # Soft normalize to -3dB to prevent clipping while maintaining dynamics
        peak = np.max(np.abs(audio_array))
        if peak > 0:
            target_peak = 0.707  # -3dB in Float32
            if peak > target_peak:  # Only normalize if needed
                audio_array = audio_array * (target_peak / peak)
        
        # Convert back to bytes
        return audio_array.astype(np.float32).tobytes()
    except Exception as e:
        print(f"⚠️ Preprocessing failed, using original: {e}")
        return audio_bytes


async def process_audio(audio_bytes: bytes, websocket: WebSocket, validator: AudioValidator):
    """Process and transcribe audio data with quality checks"""
    duration = len(audio_bytes) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
    
    if duration < MIN_AUDIO_DURATION:
        print(f"⚠️ Audio too short: {duration:.3f}s (min: {MIN_AUDIO_DURATION}s)")
        return

    try:
        # Analyze audio technical quality (NOT speech detection)
        quality = await analyze_audio_quality(audio_bytes)
        print(f"🔍 Audio Quality - Duration: {quality.get('duration', 0):.2f}s, "
              f"RMS: {quality.get('rms_energy', 0):.3f}, "
              f"Peak: {quality.get('peak_amplitude', 0):.3f}, "
              f"Invalid: {quality.get('invalid_rate', 0)*100:.1f}%")
        
        # Only skip if there's a TECHNICAL problem (not based on speech detection)
        if not quality.get('is_technically_valid', True):
            if quality.get('is_completely_silent'):
                print("⚠️ Audio is completely silent (possible technical issue)")
            elif quality.get('has_invalid_values'):
                print("⚠️ Invalid Float32 values detected (>1% out of range)")
            return
        
        # Preprocess audio for better quality
        processed_audio = await preprocess_audio(audio_bytes)
        
        base_filename = f"/Users/subrat/Desktop/Agent/audio_data/audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        print(f"💾 Processing audio: {len(processed_audio)} bytes ({duration:.2f}s)")
        
        # Save Float32 to WAV (converts to Int16 internally)
        save_float32_to_wav(processed_audio, filename=base_filename)
        
        # Transcribe - the speech recognition model will handle speech vs non-speech
        transcription = await transcribe_with_faster_whisper(processed_audio)
        
        if transcription and transcription.strip():
            print(f"📝 Transcription: {transcription}")
            
            # Get validator stats
            stats = validator.get_stats()
            
            # Send transcription back to client
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "transcription",
                    "text": transcription,
                    "timestamp": datetime.now().isoformat(),
                    "audio_quality": {
                        'duration': quality.get('duration'),
                        'rms_energy': quality.get('rms_energy'),
                        'peak_amplitude': quality.get('peak_amplitude')
                    },
                    "stats": {
                        'total_bytes': stats.get('total_bytes'),
                        'validation_rate': stats.get('validation_rate')
                    }
                })
                
                # TODO: Generate AI response and send audio back
                # response_audio = await generate_ai_response(transcription)
                # await websocket.send_bytes(response_audio)
        else:
            print("ℹ️ Empty transcription (client VAD sent non-speech, or unclear audio)")
            
    except Exception as e:
        print(f"❌ Audio processing failed: {e}")
        import traceback
        traceback.print_exc()


async def check_silence_loop(audio_data_ref: dict, last_chunk_time_ref: dict, 
                              is_receiving_ref: dict, websocket: WebSocket,
                              validator: AudioValidator):
    """Background task to check for silence timeout"""
    consecutive_silent_checks = 0
    
    try:
        while True:
            await asyncio.sleep(0.3)  # Check every 300ms
            
            if not is_receiving_ref.get('value'):
                consecutive_silent_checks = 0
                continue
                
            silence_duration = (datetime.now() - last_chunk_time_ref.get('value')).total_seconds()
            
            # Require multiple consecutive silent checks
            if silence_duration > SILENCE_TIMEOUT:
                consecutive_silent_checks += 1
            else:
                consecutive_silent_checks = 0
            
            # Process after 2 consecutive silent checks (600ms total)
            if consecutive_silent_checks >= 2 and audio_data_ref.get('value'):
                print(f"🔇 Silence confirmed ({silence_duration:.2f}s) - Processing audio...")
                await process_audio(audio_data_ref['value'], websocket, validator)
                audio_data_ref['value'] = b''
                is_receiving_ref['value'] = False
                consecutive_silent_checks = 0
                
    except asyncio.CancelledError:
        print("🛑 Silence checker cancelled")
        raise


async def handle_text_message(data: dict, lead_id_ref: dict, is_receiving_ref: dict, 
                               last_chunk_time_ref: dict, audio_data_ref: dict, 
                               websocket: WebSocket, validator: AudioValidator) -> bool:
    """Handle JSON control messages. Returns True if should break main loop."""
    msg_type = data.get("type")
    
    if msg_type == "start_conversation":
        lead_id = data.get("user_id")
        if not lead_id:
            print("⚠️ Missing user_id in start_conversation")
            await websocket.send_json({
                "type": "error",
                "message": "user_id is required"
            })
            return False
        
        lead_id_ref['value'] = lead_id
        print(f"🟢 Conversation started with lead: {lead_id}")
        is_receiving_ref['value'] = True
        last_chunk_time_ref['value'] = datetime.now()
        
        await websocket.send_json({
            "type": "status",
            "message": "ready",
            "config": {
                "sample_rate": SAMPLE_RATE,
                "format": "Float32Array",
                "silence_timeout": SILENCE_TIMEOUT,
                "min_duration": MIN_AUDIO_DURATION,
                "note": "Client-side VAD handles speech detection"
            }
        })
        return False
    
    elif msg_type == "end_conversation":
        print("🔴 End conversation requested")
        
        # Process any remaining audio
        if audio_data_ref.get('value'):
            await process_audio(audio_data_ref['value'], websocket, validator)
            audio_data_ref['value'] = b''
        
        stats = validator.get_stats()
        print(f"📊 Final Stats: {stats}")
        
        await websocket.send_json({
            "type": "status",
            "message": "conversation_ended",
            "stats": stats
        })
        return True
    
    elif msg_type == "ping":
        if websocket.application_state == WebSocketState.CONNECTED:
            stats = validator.get_stats()
            await websocket.send_json({
                "type": "pong",
                "stats": stats
            })
        return False
    
    return False


async def handle_audio_chunk(chunk: bytes, audio_data_ref: dict, is_receiving_ref: dict,
                              last_chunk_time_ref: dict, websocket: WebSocket,
                              validator: AudioValidator):
    """Handle incoming audio binary data with validation (Float32 format)"""
    
    # Validate chunk for technical correctness only
    if not validator.validate_chunk(chunk):
        return
    
    # Update state
    is_receiving_ref['value'] = True
    last_chunk_time_ref['value'] = datetime.now()
    audio_data_ref['value'] += chunk
    
    # Prevent memory overflow
    duration = len(audio_data_ref['value']) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
    if duration > MAX_AUDIO_DURATION:
        print(f"⚠️ Max audio duration reached ({duration:.1f}s), processing...")
        await process_audio(audio_data_ref['value'], websocket, validator)
        audio_data_ref['value'] = b''
        is_receiving_ref['value'] = False
    
    # Log progress every second
    if len(audio_data_ref['value']) % (SAMPLE_RATE * BYTES_PER_SAMPLE) < len(chunk):
        stats = validator.get_stats()
        print(f"🎙️ Buffer: {duration:.2f}s | "
              f"Chunks: {stats.get('total_received', 0)} | "
              f"Valid: {stats.get('validation_rate', 0)*100:.1f}% | "
              f"Avg RMS: {stats.get('avg_rms', 0):.3f}")