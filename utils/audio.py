import asyncio
from datetime import datetime
from typing import Dict, Any, Callable
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
import soundfile as sf
import numpy as np
from collections import deque
from scipy import signal

from nodes.optimized_incoming_listener import incoming_listener
from state.optimized_workflow_state import WorkflowState
from tools.stt import transcribe_with_faster_whisper

# ==================== CONFIGURATION ====================
INPUT_SAMPLE_RATE = 48000
OUTPUT_SAMPLE_RATE = 16000
NEEDS_RESAMPLING = INPUT_SAMPLE_RATE != OUTPUT_SAMPLE_RATE

SILENCE_TIMEOUT = 1.2
MAX_AUDIO_DURATION = 30
MIN_AUDIO_DURATION = 0.2
BYTES_PER_SAMPLE = 4  # Float32
MIN_ENERGY_THRESHOLD = 0.001
CHUNK_VALIDATION_WINDOW = 10

print(f"Audio Config: Input={INPUT_SAMPLE_RATE}Hz, Output={OUTPUT_SAMPLE_RATE}Hz, "
      f"Resampling={'ENABLED' if NEEDS_RESAMPLING else 'DISABLED'}")

# ==================== RESAMPLING ====================

async def resample_audio(audio_bytes: bytes, input_rate: int = INPUT_SAMPLE_RATE, 
                         output_rate: int = OUTPUT_SAMPLE_RATE) -> bytes:
    """Resample Float32 audio using scipy polyphase filtering"""
    if input_rate == output_rate:
        return audio_bytes
    
    try:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        num_output_samples = int(len(audio_array) * output_rate / input_rate)
        
        # Use scipy's efficient FFT-based resampling
        resampled = signal.resample(audio_array, num_output_samples).astype(np.float32)
        
        return resampled.tobytes()
        
    except Exception as e:
        print(f"Resampling failed: {e}")
        raise

# ==================== AUDIO I/O ====================

def save_float32_to_wav(float32_data: bytes, filename: str = "received_audio.wav", 
                        sample_rate: int = OUTPUT_SAMPLE_RATE) -> None:
    """Save Float32 audio bytes to WAV file"""
    try:
        audio_array = np.frombuffer(float32_data, dtype=np.float32)
        expected_duration = len(audio_array) / sample_rate
        print(f"Saving {len(audio_array)} samples at {sample_rate}Hz = {expected_duration:.2f}s to {filename}")
        sf.write(filename, audio_array, sample_rate, subtype='FLOAT')
    except Exception as e:
        print(f"Failed to save WAV: {e}")

# ==================== VALIDATION ====================

class AudioValidator:
    """Validates audio data for technical quality"""
    
    def __init__(self):
        self.recent_chunks = deque(maxlen=CHUNK_VALIDATION_WINDOW)
        self.total_received = 0
        self.total_valid = 0
        self.total_bytes = 0
        
    def validate_chunk(self, chunk: bytes) -> bool:
        """Validate audio chunk (Float32 format)"""
        self.total_received += 1
        
        if len(chunk) == 0 or len(chunk) % 4 != 0:
            return False
        
        try:
            audio_array = np.frombuffer(chunk, dtype=np.float32)
        except Exception:
            return False
        
        # Silent chunks are valid
        if np.all(audio_array == 0):
            return True
        
        # Check for out-of-range values
        invalid_samples = np.sum((audio_array < -1.0) | (audio_array > 1.0))
        invalid_rate = invalid_samples / len(audio_array) if len(audio_array) > 0 else 0
        
        rms = np.sqrt(np.mean(audio_array ** 2))
        max_val = np.max(np.abs(audio_array))
        
        self.recent_chunks.append({
            'size': len(chunk),
            'rms': rms,
            'max': max_val,
            'invalid_rate': invalid_rate
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

# ==================== QUALITY ANALYSIS ====================

async def analyze_audio_quality(audio_bytes: bytes, sample_rate: int = OUTPUT_SAMPLE_RATE) -> Dict[str, Any]:
    """Analyze audio technical quality"""
    try:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        rms_energy = np.sqrt(np.mean(audio_array ** 2))
        peak_amplitude = np.max(np.abs(audio_array))
        duration = len(audio_array) / sample_rate
        
        is_completely_silent = rms_energy < MIN_ENERGY_THRESHOLD
        
        invalid_samples = np.sum((audio_array < -1.0) | (audio_array > 1.0))
        invalid_rate = invalid_samples / len(audio_array) if len(audio_array) > 0 else 0
        has_invalid_values = invalid_rate > 0.01
        
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
        print(f"Audio analysis failed: {e}")
        return {'is_technically_valid': True}

async def preprocess_audio(audio_bytes: bytes) -> bytes:
    """Preprocess audio: remove DC offset, clip, normalize"""
    try:
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Remove DC offset
        audio_array = audio_array - np.mean(audio_array)
        
        # Clip to valid range
        audio_array = np.clip(audio_array, -1.0, 1.0)
        
        # Soft normalize to -3dB
        peak = np.max(np.abs(audio_array))
        if peak > 0.707:  # -3dB threshold
            audio_array = audio_array * (0.707 / peak)
        
        return audio_array.astype(np.float32).tobytes()
    except Exception as e:
        print(f"Preprocessing failed: {e}")
        return audio_bytes

# ==================== MAIN PROCESSING ====================

async def process_audio(
    audio_bytes: bytes,
    websocket: WebSocket,
    validator: AudioValidator,
    safe_send: Callable = None
):
    """
    Process audio: quality check → STT → route to incoming_listener
    
    Changes from original:
    - Added call to incoming_listener after transcription
    - incoming_listener handles everything else (AI + intent)
    """
    try:
        # === YOUR EXISTING CODE (NO CHANGES) ===
        # Resample if needed
        if NEEDS_RESAMPLING:
            processed_bytes = await resample_audio(audio_bytes, INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE)
        else:
            processed_bytes = audio_bytes

        # Analyze quality
        quality = await analyze_audio_quality(processed_bytes, OUTPUT_SAMPLE_RATE)
        if not quality.get('is_technically_valid', True):
            print("⚠️ Quality check failed")
            return

        # Preprocess
        final_audio = await preprocess_audio(processed_bytes)

        # Save WAV (optional)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"/Users/subrat/Desktop/Agent/audio_data/audio_{timestamp}.wav"
        save_float32_to_wav(final_audio, filename=filename, sample_rate=OUTPUT_SAMPLE_RATE)

        # Transcribe (STT)
        transcription = await transcribe_with_faster_whisper(final_audio)
        
        if not transcription or not transcription.strip():
            print("ℹ️ No speech detected")
            return
        
        print(f"📝 Transcription: {transcription}")
        
        # Send transcription to client
        if safe_send:
            stats = validator.get_stats()
            await safe_send(websocket, {
                "type": "transcription",
                "text": transcription,
                "timestamp": datetime.now().isoformat(),
                "audio_quality": {
                    'duration': quality.get('duration'),
                    'rms_energy': quality.get('rms_energy')
                },
                "stats": stats
            })
        
        # === NEW CODE: Route to incoming_listener ===
        
        # Get lead_id from websocket
        lead_id = getattr(websocket, 'lead_id', 'unknown')
        
        # Create state
        state = WorkflowState(
            lead_id=lead_id,
            conversation_thread=[],
            pending_action=None
        )
        
        # Prepare message data
        message_data = {
            "lead_id": lead_id,
            "message": transcription,    # Transcribed text
            "channel": "web_call",       # Indicates web call
            "audio_bytes": final_audio   # Original audio
        }
        
        # Route to incoming_listener (it handles everything else)
        await incoming_listener(state, message_data, websocket)
        
        print("✅ Audio processing complete")
            
    except Exception as e:
        print(f"❌ Audio processing failed: {e}")
        import traceback
        traceback.print_exc()

# ==================== WEBSOCKET HANDLERS ====================

async def check_silence_loop(
    audio_data_ref: dict,
    last_chunk_time_ref: dict,
    is_receiving_ref: dict,
    websocket: WebSocket,
    validator: AudioValidator,
    safe_send: Callable
):
    """Background task to check for silence timeout"""
    consecutive_silent_checks = 0
    
    try:
        while True:
            await asyncio.sleep(0.3)
            
            if not is_receiving_ref.get('value'):
                consecutive_silent_checks = 0
                continue
                
            silence_duration = (datetime.now() - last_chunk_time_ref.get('value')).total_seconds()
            
            if silence_duration > SILENCE_TIMEOUT:
                consecutive_silent_checks += 1
            else:
                consecutive_silent_checks = 0
            
            if consecutive_silent_checks >= 2 and audio_data_ref.get('value'):
                print(f"Silence detected ({silence_duration:.2f}s) - Processing...")
                await process_audio(audio_data_ref['value'], websocket, validator, safe_send)
                audio_data_ref['value'] = b''
                is_receiving_ref['value'] = False
                consecutive_silent_checks = 0
                
    except asyncio.CancelledError:
        print("Silence checker cancelled")
        raise

async def handle_text_message(
    data: dict,
    lead_id_ref: dict,
    is_receiving_ref: dict,
    last_chunk_time_ref: dict,
    audio_data_ref: dict,
    websocket: WebSocket,
    validator: AudioValidator,
    safe_send: Callable
) -> bool:
    """Handle JSON control messages"""
    msg_type = data.get("type")

    if msg_type == "start_conversation":
        lead_id = data.get("user_id")
        if not lead_id:
            print("Missing user_id")
            await safe_send(websocket, {"type": "error", "message": "user_id is required"})
            return False

        lead_id_ref['value'] = lead_id
        print(f"Conversation started: {lead_id}")
        is_receiving_ref['value'] = True
        last_chunk_time_ref['value'] = datetime.now()

        await safe_send(websocket, {
            "type": "status",
            "message": "ready",
            "config": {
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE,
                "resampling_enabled": NEEDS_RESAMPLING,
                "format": "Float32Array"
            }
        })
        return False

    elif msg_type == "end_conversation":
        print("Ending conversation")
        if audio_data_ref.get('value'):
            await process_audio(audio_data_ref['value'], websocket, validator, safe_send)
            audio_data_ref['value'] = b''

        stats = validator.get_stats()
        await safe_send(websocket, {
            "type": "status",
            "message": "conversation_ended",
            "stats": stats
        })
        return True

    elif msg_type == "ping":
        await safe_send(websocket, {"type": "pong", "stats": validator.get_stats()})
        return False

    return False

async def handle_audio_chunk(
    chunk: bytes,
    audio_data_ref: dict,
    is_receiving_ref: dict,
    last_chunk_time_ref: dict,
    websocket: WebSocket,
    validator: AudioValidator,
    safe_send: Callable
):
    """Handle incoming audio binary data"""
    
    if not validator.validate_chunk(chunk):
        return
    
    is_receiving_ref['value'] = True
    last_chunk_time_ref['value'] = datetime.now()
    audio_data_ref['value'] += chunk
    
    # Calculate duration at INPUT rate
    duration = len(audio_data_ref['value']) / (INPUT_SAMPLE_RATE * BYTES_PER_SAMPLE)
    
    if duration > MAX_AUDIO_DURATION:
        print(f"Max duration reached ({duration:.1f}s) - processing")
        await process_audio(audio_data_ref['value'], websocket, validator, safe_send)
        audio_data_ref['value'] = b''
        is_receiving_ref['value'] = False
    
    # Log progress every second
    if len(audio_data_ref['value']) % (INPUT_SAMPLE_RATE * BYTES_PER_SAMPLE) < len(chunk):
        stats = validator.get_stats()
        print(f"Buffer: {duration:.2f}s | Chunks: {stats.get('total_received', 0)} | "
              f"Valid: {stats.get('validation_rate', 0)*100:.1f}%")
        


# === KEEP ALL YOUR OTHER FUNCTIONS AS-IS ===
# - resample_audio()
# - analyze_audio_quality()
# - preprocess_audio()
# - transcribe_with_faster_whisper()
# - check_silence_loop()
# - handle_text_message()
# - etc.