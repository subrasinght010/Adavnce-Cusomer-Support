import asyncio
import io
import tempfile
import numpy as np
import soundfile as sf
import os

# -------------------------------
# Configuration - Choose Whisper Backend
# -------------------------------
USE_WHISPER_CPP = os.getenv("USE_WHISPER_CPP", "false").lower() == "true"

if USE_WHISPER_CPP:
    # Whisper.cpp backend (faster, less RAM)
    try:
        from pywhispercpp.model import Model
        model = Model('medium', n_threads=8)
        print(f"✅ Whisper.cpp loaded: Medium model (Optimized C++)")
        BACKEND = "cpp"
    except ImportError:
        print("⚠️ pywhispercpp not installed. Install: pip install pywhispercpp")
        print("⚠️ Falling back to original Whisper...")
        USE_WHISPER_CPP = False

if not USE_WHISPER_CPP:
    # Original Whisper backend (PyTorch)
    import whisper
    import torch
    
    # MPS has compatibility issues with Whisper - using CPU for stability
    device = "cpu"
    model = whisper.load_model("medium").to(device)
    print(f"🎯 Whisper (PyTorch) using: {device.upper()} (CPU mode for stability)")
    BACKEND = "pytorch"

# Models Reference:
# tiny   - 39M params  - ~1 GB RAM - 10x speed
# base   - 74M params  - ~1 GB RAM - 7x speed  
# small  - 244M params - ~2 GB RAM - 4x speed
# medium - 769M params - ~5 GB RAM - 2x speed (pytorch) / ~1.6 GB (cpp)
# large  - 1550M params- ~10 GB RAM- 1x speed (pytorch) / ~4 GB (cpp)

# -------------------------------
# Utilities
# -------------------------------
async def ensure_pcm_bytes(audio_bytes: bytes, target_rate: int = 16000) -> bytes:
    """Ensure audio bytes are PCM16 at target sample rate."""
    try:
        arr = np.frombuffer(audio_bytes, dtype=np.int16)
        if arr.ndim > 1:
            arr = arr[:, 0]
        return arr.tobytes()
    except Exception:
        pass

    try:
        audio_np, sr = sf.read(io.BytesIO(audio_bytes))
        if audio_np.ndim > 1:
            audio_np = audio_np[:, 0]

        if sr != target_rate:
            import librosa
            audio_np = librosa.resample(audio_np.astype(np.float32), orig_sr=sr, target_sr=target_rate)
            audio_np = (audio_np * 32767).astype(np.int16)
        elif audio_np.dtype != np.int16:
            audio_np = (audio_np * 32767).astype(np.int16)

        return audio_np.tobytes()
    except Exception as e:
        print(f"❌ Failed to convert to PCM16: {e}")
        return audio_bytes


# -------------------------------
# Transcription
# -------------------------------
async def transcribe_with_faster_whisper(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """Transcribe audio bytes using selected Whisper backend."""
    try:
        if BACKEND == "cpp":
            # Whisper.cpp - convert bytes to int16 numpy array
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Convert to mono if stereo
            if audio_np.ndim > 1:
                audio_np = audio_np[:, 0]
            
            # Create temporary PCM16 WAV file (whisper.cpp needs a file)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_np, sample_rate, subtype='PCM_16')
                temp_path = tmp_file.name
            
            # Transcribe from file
            result = model.transcribe(temp_path)
            
            # Clean up temp file immediately
            try:
                os.unlink(temp_path)
            except:
                print(f"⚠️ Failed to delete temp file: {temp_path}")
                pass
            
            # Handle different return types
            if isinstance(result, str):
                return result.strip()
            elif isinstance(result, dict):
                return result.get('text', '').strip()
            else:
                return str(result).strip()
        
        else:
            # PyTorch Whisper - convert bytes to float32 numpy array
            audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
            
            # Make writable copy
            audio_np = audio_np.copy()
            
            # Transcribe directly from numpy array
            result = model.transcribe(audio_np, language="en", fp16=False)
            return result.get("text", "").strip()
        
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        import traceback
        traceback.print_exc()
        return ""


# -------------------------------
# Test Function (Optional)
# -------------------------------
async def test_speech_to_text():
    """Test speech-to-text with a sample WAV file."""
    try:
        sample_file = "audio_data/sample.wav"
        
        if not os.path.exists(sample_file):
            print(f"⚠️ Sample file not found: {sample_file}")
            return

        # Read audio based on backend needs
        if BACKEND == "cpp":
            audio_np, sr = sf.read(sample_file, dtype="int16")
        else:
            audio_np, sr = sf.read(sample_file, dtype="float32")
        
        print(f"🎚️ Loaded: {sample_file}, SR: {sr}, Shape: {audio_np.shape}")

        audio_bytes = audio_np.tobytes()
        transcription = await transcribe_with_faster_whisper(audio_bytes, sample_rate=sr)
        print(f"📝 Transcription [{BACKEND}]: {transcription}")

    except Exception as e:
        print(f"❌ Test error: {e}")


# -------------------------------
# Run Test
# -------------------------------
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Testing Whisper Backend: {BACKEND.upper()}")
    print(f"{'='*60}\n")
    asyncio.run(test_speech_to_text())