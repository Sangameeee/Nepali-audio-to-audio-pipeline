# ==============================================================================
# Voice Assistant - Pydantic Schemas (Request/Response Models)
# File: backend/app/schemas.py
# ==============================================================================

from typing import List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request model for the main /api/query endpoint in dev (text-only) mode."""
    text: str = Field(..., description="User query text (dev mode)")
    lang: str = Field(default="en", description="Language: 'en', 'ne', or 'auto'")
    is_dev: bool = Field(default=True, description="Dev mode flag (skip ASR/TTS)")


class QueryResponse(BaseModel):
    """Response model for the main /api/query and /api/dev_process endpoints."""
    transcript: str = Field(default="", description="Original transcription from ASR")
    detected_lang: str = Field(default="en", description="Detected language: 'en' or 'ne'")
    answer_english: str = Field(default="", description="Response generated in English")
    final_text: str = Field(default="", description="Final response text (possibly translated)")
    final_lang: str = Field(default="en", description="Language of the final response")
    audio_base64: Optional[str] = Field(default=None, description="Base64-encoded audio response")
    input_audio_base64: Optional[str] = Field(default=None, description="Base64-encoded input audio for playback")
    processing_steps: List[str] = Field(default_factory=list, description="Log of processing steps")
    rag_sources: List[dict] = Field(default_factory=list, description="RAG source citations")
    error: Optional[str] = Field(default=None, description="Error message if something failed")


class TranscribeResponse(BaseModel):
    """Response model for the /api/transcribe endpoint."""
    transcript: str = Field(..., description="Transcribed text from audio")
    detected_lang: str = Field(default="en", description="Detected language code")


class SynthesizeRequest(BaseModel):
    """Request model for the /api/synthesize endpoint."""
    text: str = Field(..., description="Text to synthesize into speech")
    lang: str = Field(default="en", description="Target language for TTS: 'en' or 'ne'")
    use_online_tts: bool = Field(default=False, description="Use Online TTS")


class SynthesizeResponse(BaseModel):
    """Response model for the /api/synthesize endpoint."""
    audio_base64: str = Field(..., description="Base64-encoded audio output")
    lang: str = Field(default="en", description="Language of the synthesized audio")


class TranslateRequest(BaseModel):
    """Request model for the /api/translate endpoint."""
    text: str = Field(..., description="Text to translate")
    source_lang: str = Field(default="en", description="Source language: 'en' or 'ne'")
    target_lang: str = Field(default="ne", description="Target language: 'en' or 'ne'")


class TranslateResponse(BaseModel):
    """Response model for the /api/translate endpoint."""
    original_text: str = Field(..., description="Original input text")
    translated_text: str = Field(..., description="Translated output text")
    source_lang: str = Field(default="en", description="Source language")
    target_lang: str = Field(default="ne", description="Target language")


class HealthResponse(BaseModel):
    """Response model for the /api/health endpoint."""
    status: str = Field(default="ok")
    app_name: str = Field(default="Voice Assistant")
    version: str = Field(default="0.1.0")
    device: str = Field(default="cpu")
    models_loaded: dict = Field(default_factory=dict, description="Status of loaded models")
