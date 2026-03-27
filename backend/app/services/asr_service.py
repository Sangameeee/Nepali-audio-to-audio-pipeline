# ==============================================================================
# Voice Assistant - ASR (Automatic Speech Recognition) Service
# File: backend/app/services/asr_service.py
#
# Purpose:
#   Handles all speech-to-text transcription. Supports:
#     1. English ASR: placeholder (to be integrated later)
#     2. Nepali ASR: Remote API call to Colab server via ngrok
#     3. Automatic language detection via Devanagari script heuristic
#
# Communication:
#   - Called by: routers/query.py (via dependency injection)
#   - Calls: Remote ASR API for Nepali, utils.py for audio preprocessing
#   - Input: audio file path (str) + language code ("en", "ne", "auto")
#   - Output: dict {"transcript": str, "detected_lang": str}
# ==============================================================================

import logging
import os
from pathlib import Path
from typing import Optional

import requests

from app.config import Settings

logger = logging.getLogger("voice_assistant.asr")


class ASRService:
    """
    Automatic Speech Recognition service.
    Nepali ASR uses a remote FastAPI server (Colab + ngrok).
    English ASR is a placeholder (to be implemented later).
    """

    def __init__(self, settings: Settings):
        """
        Args:
            settings: Application settings containing API URLs and device info.
        """
        self.settings = settings
        self.device = settings.DEVICE
        self._colab_api_url = settings.ASR_COLAB_API_URL
        self._decoder = settings.ASR_DECODER

        logger.info(
            f"ASR Service initialized (device={self.device}, "
            f"colab_url={self._colab_api_url})"
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def transcribe(self, audio_path: str, lang: str = "en") -> dict:
        """
        Main entry point for transcription.

        Workflow:
          1. If lang == "auto": detect language first, then route.
          2. If lang == "en": use mock English ASR (placeholder).
          3. If lang == "ne": use remote Nepali ASR API.

        Args:
            audio_path: Path to the preprocessed audio file (16kHz mono WAV).
            lang: Language code – "en", "ne", or "auto".

        Returns:
            dict: {"transcript": str, "detected_lang": "en"|"ne"}
        """
        detected_lang = lang

        if lang == "auto":
            detected_lang = await self._detect_language(audio_path)
            logger.info(f"Auto-detected language: {detected_lang}")

        if detected_lang == "en":
            transcript = await self._transcribe_english(audio_path)
        elif detected_lang == "ne":
            transcript = await self._transcribe_nepali(audio_path)
        else:
            logger.warning(
                f"Unsupported language '{detected_lang}', falling back to English ASR."
            )
            detected_lang = "en"
            transcript = await self._transcribe_english(audio_path)

        return {
            "transcript": transcript,
            "detected_lang": detected_lang,
        }

    def check_server_health(self) -> dict:
        """
        Check if the remote ASR server is reachable.

        Returns:
            dict with server health info or error message.
        """
        try:
            health_url = f"{self._colab_api_url.rstrip('/')}/health"
            resp = requests.get(health_url, timeout=10)
            resp.raise_for_status()
            info = resp.json()
            logger.info(
                f"ASR server reachable — device: {info.get('device')} | "
                f"GPU: {info.get('gpu_name')}"
            )
            return {"status": "ok", **info}
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot reach ASR server at {self._colab_api_url}")
            return {"status": "error", "message": "Server unreachable"}
        except Exception as e:
            logger.error(f"ASR health check failed: {e}")
            return {"status": "error", "message": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────────────────────────

    async def _transcribe_english(self, audio_path: str) -> str:
        """
        Transcribe audio using English ASR.
        Currently a placeholder — to be integrated later.

        Args:
            audio_path: Path to 16kHz mono WAV file.
        Returns:
            Transcribed English text.
        """
        logger.info(f"[MOCK] Transcribing English audio: {audio_path}")
        return "English ASR is not yet integrated. Please select Nepali or Auto for ASR."

    async def _transcribe_nepali(self, audio_path: str) -> str:
        """
        Transcribe audio using the remote Nepali ASR API (Colab + ngrok).

        Sends the audio file to the remote server and returns the transcription.

        Args:
            audio_path: Path to 16kHz mono WAV file.
        Returns:
            Transcribed Nepali text.
        """
        if not os.path.isfile(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return "Error: Audio file not found."

        transcribe_url = (
            f"{self._colab_api_url.rstrip('/')}/transcribe"
            f"?decoder={self._decoder}"
        )

        try:
            with open(audio_path, "rb") as f:
                files = {
                    "audio": (os.path.basename(audio_path), f, "audio/wav")
                }
                response = requests.post(
                    transcribe_url, files=files, timeout=120
                )

            if response.status_code == 200:
                data = response.json()
                transcript = data.get("transcription", "")
                logger.info(
                    f"Nepali ASR transcription: '{transcript[:80]}...'"
                )
                return transcript
            else:
                detail = response.json().get("detail", response.text)
                logger.error(
                    f"ASR server error {response.status_code}: {detail}"
                )
                return f"ASR Error: {detail}"

        except requests.exceptions.Timeout:
            logger.error(f"ASR request timed out for {audio_path}")
            return "ASR Error: Request timed out. Try a shorter audio file."
        except requests.exceptions.ConnectionError:
            logger.error(
                f"Cannot reach ASR server at {self._colab_api_url}"
            )
            return (
                "ASR Error: Cannot reach ASR server. "
                "Make sure the Colab notebook is running."
            )
        except Exception as e:
            logger.error(f"Unexpected ASR error: {e}")
            return f"ASR Error: {str(e)}"

    async def _detect_language(self, audio_path: str) -> str:
        """
        Detect the language of the audio.

        Simple heuristic: default to 'ne' since the remote ASR
        server handles Nepali. Can be enhanced with actual detection later.

        Args:
            audio_path: Path to audio file.
        Returns:
            Language code: "en" or "ne"
        """
        # Default to Nepali since we have a real Nepali ASR backend
        logger.info("Auto-detection defaulting to 'ne' (Nepali ASR available).")
        return "ne"

    def cleanup(self):
        """Release model resources. Called during app shutdown."""
        logger.info("ASR Service cleaned up.")
