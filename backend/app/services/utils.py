# ==============================================================================
# Vani - Utility Functions
# File: backend/app/services/utils.py
#
# Purpose:
#   Common utility functions used across all services:
#     - Audio format conversion (MP3/M4A/OGG → 16kHz mono WAV)
#     - Temporary file management
#     - Base64 encoding/decoding for audio
#     - File validation (size, type)
#
# Communication:
#   - Called by: asr_service.py, tts_service.py, routers/query.py
#   - Uses: pydub (with ffmpeg) for audio conversion, or wave/audioop as fallback
#
# Dependencies:
#   - pydub: pip install pydub
#   - ffmpeg: sudo apt install ffmpeg (system package)
#   - Or: librosa as alternative for audio processing
# ==============================================================================

import base64
import logging
import os
import shutil
import tempfile
import wave
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("vani.utils")


def validate_audio_file(filename: str, file_size: int, allowed_extensions: list, max_size: int) -> Tuple[bool, str]:
    """
    Validate an uploaded audio file.

    Checks:
      1. File extension is in the allowed list.
      2. File size is within the maximum limit.

    Args:
        filename: Original filename from upload.
        file_size: Size in bytes.
        allowed_extensions: List of allowed extensions (e.g., [".wav", ".mp3"]).
        max_size: Maximum file size in bytes.

    Returns:
        Tuple of (is_valid: bool, error_message: str).
        If valid, error_message is empty.
    """
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        return False, f"Unsupported audio format '{ext}'. Allowed: {', '.join(allowed_extensions)}"
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File too large ({file_size / (1024 * 1024):.1f}MB). Maximum: {max_mb:.0f}MB."
    return True, ""


async def save_upload_to_temp(upload_file, temp_dir: str) -> str:
    """
    Save an uploaded file to a temporary location.

    Args:
        upload_file: FastAPI UploadFile object.
        temp_dir: Directory for temporary files.

    Returns:
        Path to the saved temporary file.
    """
    os.makedirs(temp_dir, exist_ok=True)
    ext = Path(upload_file.filename).suffix.lower()
    tmp = tempfile.NamedTemporaryFile(
        suffix=ext, dir=temp_dir, delete=False
    )
    content = await upload_file.read()
    tmp.write(content)
    tmp.close()
    logger.info(f"Saved upload to temp: {tmp.name} ({len(content)} bytes)")
    return tmp.name


def convert_to_wav_16k(input_path: str, temp_dir: str) -> str:
    """
    Convert an audio file to 16kHz mono WAV format (required by most ASR models).

    Uses pydub (with ffmpeg backend) for format conversion.
    Falls back to a simple copy if the file is already WAV.

    Args:
        input_path: Path to the input audio file.
        temp_dir: Directory for the output file.

    Returns:
        Path to the converted WAV file.

    Note:
        Requires ffmpeg to be installed on the system:
          Ubuntu/Debian: sudo apt install ffmpeg
          macOS: brew install ffmpeg
    """
    output_path = tempfile.NamedTemporaryFile(
        suffix=".wav", dir=temp_dir, delete=False
    ).name

    try:
        # Try pydub (requires ffmpeg)
        from pydub import AudioSegment

        audio = AudioSegment.from_file(input_path)
        # Convert to mono, 16kHz, 16-bit
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        audio.export(output_path, format="wav")
        logger.info(f"Converted audio to 16kHz WAV: {output_path}")
        return output_path

    except ImportError:
        logger.warning("pydub not installed. Attempting basic WAV handling.")

        # Fallback: if input is already WAV, just copy it
        if input_path.lower().endswith(".wav"):
            shutil.copy2(input_path, output_path)
            logger.info(f"Copied WAV file to: {output_path}")
            return output_path
        else:
            raise RuntimeError(
                "Cannot convert non-WAV audio without pydub. "
                "Install pydub: pip install pydub"
            )

    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        # Last resort: copy the file as-is
        shutil.copy2(input_path, output_path)
        return output_path


def encode_audio_base64(file_path: str) -> str:
    """
    Read an audio file and return its base64 representation.

    Args:
        file_path: Path to the audio file.

    Returns:
        Base64-encoded string (without data URI prefix).
    """
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def decode_audio_base64(base64_string: str, output_path: str) -> str:
    """
    Decode a base64 audio string and save to file.

    Args:
        base64_string: Base64-encoded audio (may include data URI prefix).
        output_path: Path to save the decoded file.

    Returns:
        Path to the saved file.
    """
    # Strip data URI prefix if present
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]

    audio_bytes = base64.b64decode(base64_string)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    return output_path


def cleanup_temp_files(temp_dir: str, max_age_seconds: int = 3600):
    """
    Clean up temporary files older than max_age_seconds.

    Called periodically or at shutdown to prevent temp directory bloat.

    Args:
        temp_dir: Path to the temporary directory.
        max_age_seconds: Maximum age of files to keep (default: 1 hour).
    """
    import time

    if not os.path.exists(temp_dir):
        return

    now = time.time()
    removed = 0
    for filename in os.listdir(temp_dir):
        filepath = os.path.join(temp_dir, filename)
        if os.path.isfile(filepath):
            file_age = now - os.path.getmtime(filepath)
            if file_age > max_age_seconds:
                try:
                    os.remove(filepath)
                    removed += 1
                except OSError as e:
                    logger.warning(f"Could not remove temp file {filepath}: {e}")

    if removed > 0:
        logger.info(f"Cleaned up {removed} temp files from {temp_dir}")


def get_audio_duration(file_path: str) -> float:
    """
    Get the duration of a WAV audio file in seconds.

    Args:
        file_path: Path to WAV file.

    Returns:
        Duration in seconds.
    """
    try:
        with wave.open(file_path, "r") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)
    except Exception as e:
        logger.warning(f"Could not determine audio duration: {e}")
        return 0.0
