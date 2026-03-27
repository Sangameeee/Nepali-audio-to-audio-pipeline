# ==============================================================================
# Voice Assistant - Text-to-Speech (TTS) Service
# File: backend/app/services/tts_service.py
#
# Purpose:
#   Generates speech audio from text using gTTS (Google Text-to-Speech).
#   Supports both English and Nepali output with speed adjustment via pydub.
#
# Communication:
#   - Called by: routers/query.py
#   - Input: text (str) + language ("en" or "ne")
#   - Output: base64-encoded WAV audio string
# ==============================================================================

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.config import Settings

logger = logging.getLogger("voice_assistant.tts")


class TTSService:
    """
    Text-to-Speech service using gTTS + pydub for speed adjustment.
    """

    def __init__(self, settings: Settings):
        """
        Args:
            settings: App settings (output dir, etc.).
        """
        self.settings = settings
        self.device = settings.DEVICE

        # Ensure output directory exists
        os.makedirs(settings.TTS_OUTPUT_DIR, exist_ok=True)

        logger.info("TTS Service initialized (gTTS + pydub).")

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def synthesize(self, text: str, lang: str = "en", use_online: bool = False) -> str:
        """
        Synthesize speech from text.

        Args:
            text: Text to convert to speech.
            lang: Target language ("en" or "ne").
            use_online: Whether to use the online TTS API.

        Returns:
            Base64-encoded audio string with data URI prefix:
            "data:audio/mp3;base64,..."
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to TTS. Returning empty audio.")
            return ""

        try:
            if use_online:
                audio_path = await self._synthesize_online(text, lang)
            else:
                audio_path = await self._generate_audio(text, lang)
            audio_base64 = self._encode_audio_base64(audio_path)

            # Clean up temp file
            if os.path.exists(audio_path):
                os.remove(audio_path)

            return f"data:audio/mp3;base64,{audio_base64}"

        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return ""

    async def _synthesize_online(self, text: str, lang: str) -> str:
        """
        Placeholder for ElevenLabs API or other online TTS.
        Currently falls back to gTTS but logs the action.
        """
        logger.info(f"ElevenLabs API placeholder called for text: '{text[:50]}...' lang: {lang}")
        # Falling back to gTTS for now to keep UI functioning
        return await self._generate_audio(text, lang)

    async def _generate_audio(self, text: str, lang: str) -> str:
        """
        Generate audio file from text using gTTS with pydub speed adjustment.

        For Nepali: 1.3x speed for more natural sound
        For English: 1.1x speed for slightly crisper sound

        Args:
            text: Text to synthesize.
            lang: Target language ("en" or "ne").
        Returns:
            Path to generated audio file (MP3).
        """
        from gtts import gTTS
        from pydub import AudioSegment

        unique_id = uuid4().hex[:8]

        # Map language codes for gTTS
        gtts_lang = "ne" if lang == "ne" else "en"

        # Speed factor: Nepali gets a bigger boost for natural sound
        speed_factor = 1.3 if lang == "ne" else 1.1

        # Generate initial MP3 with gTTS
        raw_mp3_path = os.path.join(
            self.settings.TTS_OUTPUT_DIR,
            f"tts_raw_{unique_id}.mp3"
        )
        final_mp3_path = os.path.join(
            self.settings.TTS_OUTPUT_DIR,
            f"tts_{unique_id}.mp3"
        )

        try:
            tts = gTTS(text, lang=gtts_lang)
            tts.save(raw_mp3_path)
            logger.info(f"gTTS generated raw audio: {raw_mp3_path}")

            # Speed up with pydub for more natural sound
            audio = AudioSegment.from_mp3(raw_mp3_path)
            faster_audio = audio.speedup(playback_speed=speed_factor)

            # Adjust sample width and frame rate for better quality
            faster_audio = faster_audio.set_frame_rate(24000)

            faster_audio.export(final_mp3_path, format="mp3")
            logger.info(
                f"TTS audio sped up ({speed_factor}x) and saved: {final_mp3_path}"
            )

            # Clean up raw file
            if os.path.exists(raw_mp3_path):
                os.remove(raw_mp3_path)

            return final_mp3_path

        except Exception as e:
            logger.error(f"gTTS generation error: {e}")
            # Clean up on error
            for path in [raw_mp3_path, final_mp3_path]:
                if os.path.exists(path):
                    os.remove(path)
            raise

    def _encode_audio_base64(self, audio_path: str) -> str:
        """
        Read an audio file and encode it as base64.

        Args:
            audio_path: Path to audio file (MP3 or WAV).
        Returns:
            Base64-encoded string.
        """
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        return base64.b64encode(audio_bytes).decode("utf-8")

    def cleanup(self):
        """Release TTS resources and clean up temp files."""
        output_dir = self.settings.TTS_OUTPUT_DIR
        if os.path.exists(output_dir):
            for f in os.listdir(output_dir):
                if f.startswith("tts") and f.endswith(".mp3"):
                    try:
                        os.remove(os.path.join(output_dir, f))
                    except OSError:
                        pass

        logger.info("TTS Service cleaned up.")
