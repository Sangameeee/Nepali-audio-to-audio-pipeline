# ==============================================================================
# Voice Assistant - API Router
# File: backend/app/routers/query.py
#
# Endpoints:
#   - POST /api/query        : Main endpoint (audio or text → full pipeline)
#   - POST /api/transcribe   : Audio → text only
#   - POST /api/synthesize   : Text → audio only
#   - POST /api/translate    : Text → translated text
#   - POST /api/dev_process  : Dev mode (text → text, no ASR/TTS)
#   - GET  /api/health       : Health check
# ==============================================================================

import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.services.asr_service import ASRService
from app.services.processor import ProcessorService
from app.services.translator import TranslatorService
from app.services.tts_service import TTSService
from app.services.utils import (
    cleanup_temp_files,
    convert_to_wav_16k,
    save_upload_to_temp,
    validate_audio_file,
)

logger = logging.getLogger("voice_assistant.router")

router = APIRouter(prefix="/api", tags=["Voice Assistant API"])


class AskRequest(BaseModel):
    question: str = Field(..., description="Question text")
    min_cosine: Optional[float] = Field(default=-1)
    days_filter: Optional[int] = Field(default=-1)
    top_k: Optional[int] = Field(default=-1)


# ──────────────────────────────────────────────────────────────────────────
# Dependency helpers
# ──────────────────────────────────────────────────────────────────────────

def get_asr_service(request: Request) -> ASRService:
    return request.app.state.asr_service

def get_processor_service(request: Request) -> ProcessorService:
    return request.app.state.processor_service

def get_translator_service(request: Request) -> TranslatorService:
    return request.app.state.translator_service

def get_tts_service(request: Request) -> TTSService:
    return request.app.state.tts_service


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)):
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        device=settings.DEVICE,
        models_loaded={
            "asr_english": f"remote via Colab /ask_audio ({settings.RAG_COLAB_API_URL})",
            "asr_nepali": f"remote ({settings.ASR_COLAB_API_URL})",
            "translator": "deep-translator",
            "tts": "gTTS + pydub",
            "rag": f"remote ({settings.RAG_COLAB_API_URL})",
        },
    )


@router.post("/ask")
async def ask_text(
    body: AskRequest,
    processor: ProcessorService = Depends(get_processor_service),
):
    """
    Colab-compatible text endpoint.
    Returns: transcription=None, question, answer, sources.
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        answer, sources = await processor._handle_rag_query(question)
        return {
            "transcription": None,
            "question": question,
            "answer": answer,
            "sources": sources,
        }
    except Exception as e:
        logger.error(f"/ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask_audio")
async def ask_audio(
    audio: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    processor: ProcessorService = Depends(get_processor_service),
):
    """
    Colab-compatible English audio endpoint.
    Returns transcription + question + answer + sources.
    """
    temp_path = None
    wav_path = None
    try:
        content = await audio.read()
        await audio.seek(0)
        is_valid, error_msg = validate_audio_file(
            audio.filename,
            len(content),
            settings.ALLOWED_AUDIO_EXTENSIONS,
            settings.MAX_UPLOAD_SIZE,
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        temp_path = await save_upload_to_temp(audio, settings.TEMP_DIR)
        try:
            wav_path = convert_to_wav_16k(temp_path, settings.TEMP_DIR)
        except Exception:
            wav_path = temp_path

        data = await processor.ask_audio_with_rag(wav_path)
        return {
            "transcription": data.get("transcription", ""),
            "question": data.get("question", ""),
            "answer": data.get("answer", ""),
            "sources": data.get("sources", []),
            "fallback": data.get("fallback", False),
            "message": data.get("message"),
            "params_used": data.get("params_used"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/ask_audio error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for path in [temp_path, wav_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


@router.post("/query")
async def process_query(
    request: Request,
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    lang: str = Form("en"),
    is_dev: bool = Form(False),
    use_online_tts: bool = Form(False),
    settings: Settings = Depends(get_settings),
    asr_service: ASRService = Depends(get_asr_service),
    processor: ProcessorService = Depends(get_processor_service),
    translator: TranslatorService = Depends(get_translator_service),
    tts_service: TTSService = Depends(get_tts_service),
):
    """
    Main query endpoint – orchestrates the full pipeline.
    Streams NDJSON updates incrementally to the frontend.
    """
    saved_audio_path = None
    error_response = None

    if not is_dev:
        if not audio:
            error_response = {"type": "error", "error": "Audio file is required in audio mode."}
        else:
            try:
                content = await audio.read()
                await audio.seek(0)
                is_valid, error_msg = validate_audio_file(
                    audio.filename, len(content),
                    settings.ALLOWED_AUDIO_EXTENSIONS,
                    settings.MAX_UPLOAD_SIZE,
                )
                if not is_valid:
                    error_response = {"type": "error", "error": error_msg}
                else:
                    saved_audio_path = await save_upload_to_temp(audio, settings.TEMP_DIR)
            except Exception as e:
                error_response = {"type": "error", "error": f"Failed to read uploaded file: {str(e)}"}

    async def generate():
        try:
            if error_response:
                yield json.dumps(error_response) + "\n"
                return

            transcript = ""
            detected_lang = lang

            if is_dev:
                if not text:
                    yield json.dumps({"type": "error", "error": "Text is required in dev mode."}) + "\n"
                    return
                transcript = text
                if lang == "auto":
                    if any("\u0900" <= ch <= "\u097F" for ch in text):
                        detected_lang = "ne"
                    else:
                        detected_lang = "en"
                    yield json.dumps({"type": "step", "message": f"Dev mode: Auto-detected language as '{detected_lang}'"}) + "\n"
                else:
                    detected_lang = lang
                yield json.dumps({"type": "step", "message": f"Dev mode: Using text input (lang={detected_lang})"}) + "\n"
                
                yield json.dumps({
                    "type": "asr",
                    "transcript": transcript,
                    "detected_lang": detected_lang
                }) + "\n"

            else:
                yield json.dumps({"type": "step", "message": "Received audio file."}) + "\n"
                yield json.dumps({"type": "step", "message": "Saved audio to temp storage."}) + "\n"

                temp_path = saved_audio_path

                try:
                    wav_path = convert_to_wav_16k(temp_path, settings.TEMP_DIR)
                    yield json.dumps({"type": "step", "message": "Converted audio to 16kHz mono WAV."}) + "\n"
                except Exception as e:
                    logger.warning(f"Audio conversion failed, using original: {e}")
                    wav_path = temp_path

                try:
                    with open(wav_path, "rb") as f:
                        input_bytes = f.read()
                    input_audio_base64 = f"data:audio/wav;base64,{base64.b64encode(input_bytes).decode('utf-8')}"
                    yield json.dumps({
                        "type": "input_audio",
                        "input_audio_base64": input_audio_base64
                    }) + "\n"
                except Exception as e:
                    logger.warning(f"Could not encode input audio: {e}")

                # For English audio, use Colab's unified /ask_audio path:
                # English ASR -> RAG + LLM in one call.
                if lang == "en":
                    yield json.dumps({"type": "step", "message": "Calling Colab English ASR + RAG pipeline..."}) + "\n"
                    colab_result = await processor.ask_audio_with_rag(wav_path)
                    transcript = colab_result.get("transcription", "")
                    detected_lang = "en"
                    answer_english = colab_result.get("answer", "")
                    rag_sources = colab_result.get("sources", [])
                    yield json.dumps({"type": "step", "message": "Colab ASR + RAG processing complete."}) + "\n"
                    yield json.dumps({
                        "type": "asr",
                        "transcript": transcript,
                        "detected_lang": detected_lang
                    }) + "\n"

                    yield json.dumps({
                        "type": "process",
                        "answer_english": answer_english,
                        "rag_sources": rag_sources
                    }) + "\n"

                    final_text = answer_english
                    yield json.dumps({
                        "type": "final_text",
                        "final_text": final_text,
                        "final_lang": "en"
                    }) + "\n"

                    for path in [temp_path, wav_path]:
                        if os.path.exists(path):
                            try:
                                os.remove(path)
                            except OSError:
                                pass

                    yield json.dumps({"type": "step", "message": f"Generating speech audio (Online TTS: {use_online_tts})..."}) + "\n"
                    audio_base64 = await tts_service.synthesize(final_text, "en", use_online=use_online_tts)
                    yield json.dumps({
                        "type": "audio",
                        "audio_base64": audio_base64
                    }) + "\n"
                    yield json.dumps({"type": "step", "message": "Speech synthesis complete."}) + "\n"
                    yield json.dumps({"type": "done"}) + "\n"
                    return

                yield json.dumps({"type": "step", "message": "Transcribing audio..."}) + "\n"
                asr_result = await asr_service.transcribe(wav_path, lang)
                transcript = asr_result["transcript"]
                detected_lang = asr_result["detected_lang"]
                yield json.dumps({"type": "step", "message": f"Transcription complete (lang={detected_lang})."}) + "\n"

                yield json.dumps({
                    "type": "asr",
                    "transcript": transcript,
                    "detected_lang": detected_lang
                }) + "\n"

                for path in [temp_path, wav_path]:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass

            english_text = transcript
            if detected_lang == "ne":
                yield json.dumps({"type": "step", "message": "Translating Nepali transcript to English for processing..."}) + "\n"
                english_text = await translator.translate(transcript, "ne", "en")
                yield json.dumps({"type": "step", "message": "Translation to English complete."}) + "\n"

            yield json.dumps({"type": "step", "message": "Processing query..."}) + "\n"
            result = await processor.process_query(
                text=transcript,
                source_lang=detected_lang,
                english_text=english_text,
            )
            answer_english = result["answer_english"]
            rag_sources = result.get("rag_sources", [])
            for s in result["steps"]:
                yield json.dumps({"type": "step", "message": s}) + "\n"

            yield json.dumps({
                "type": "process",
                "answer_english": answer_english,
                "rag_sources": rag_sources
            }) + "\n"

            if detected_lang == "ne":
                yield json.dumps({"type": "step", "message": "Translating response to Nepali..."}) + "\n"
                final_text = await translator.translate(answer_english, "en", "ne")
                yield json.dumps({"type": "step", "message": "Translation to Nepali complete."}) + "\n"
            else:
                final_text = answer_english

            yield json.dumps({
                "type": "final_text",
                "final_text": final_text,
                "final_lang": "ne" if detected_lang == "ne" else "en"
            }) + "\n"

            if not is_dev:
                yield json.dumps({"type": "step", "message": f"Generating speech audio (Online TTS: {use_online_tts})..."}) + "\n"
                audio_base64 = await tts_service.synthesize(final_text, "ne" if detected_lang == "ne" else "en", use_online=use_online_tts)
                yield json.dumps({
                    "type": "audio",
                    "audio_base64": audio_base64
                }) + "\n"
                yield json.dumps({"type": "step", "message": "Speech synthesis complete."}) + "\n"
            else:
                yield json.dumps({"type": "step", "message": "Dev mode: Skipping TTS synthesis."}) + "\n"

            yield json.dumps({"type": "done"}) + "\n"

        except Exception as e:
            logger.error(f"Query processing error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    lang: str = Form("en"),
    settings: Settings = Depends(get_settings),
    asr_service: ASRService = Depends(get_asr_service),
):
    """Transcribe-only endpoint. Takes audio file and returns text."""
    try:
        content = await audio.read()
        await audio.seek(0)
        is_valid, error_msg = validate_audio_file(
            audio.filename, len(content),
            settings.ALLOWED_AUDIO_EXTENSIONS,
            settings.MAX_UPLOAD_SIZE,
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        temp_path = await save_upload_to_temp(audio, settings.TEMP_DIR)

        try:
            wav_path = convert_to_wav_16k(temp_path, settings.TEMP_DIR)
        except Exception:
            wav_path = temp_path

        result = await asr_service.transcribe(wav_path, lang)

        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        return TranscribeResponse(
            transcript=result["transcript"],
            detected_lang=result["detected_lang"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(
    body: SynthesizeRequest,
    tts_service: TTSService = Depends(get_tts_service),
):
    """TTS-only endpoint. Takes text and language, returns audio."""
    try:
        audio_base64 = await tts_service.synthesize(body.text, body.lang, use_online=body.use_online_tts)
        if not audio_base64:
            raise HTTPException(status_code=500, detail="TTS synthesis failed.")
        return SynthesizeResponse(audio_base64=audio_base64, lang=body.lang)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(
    body: TranslateRequest,
    translator: TranslatorService = Depends(get_translator_service),
):
    """
    Standalone translation endpoint.
    Translates text between English and Nepali.
    """
    try:
        translated = await translator.translate(
            body.text, body.source_lang, body.target_lang
        )
        return TranslateResponse(
            original_text=body.text,
            translated_text=translated,
            source_lang=body.source_lang,
            target_lang=body.target_lang,
        )
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dev_process")
async def dev_process(
    body: QueryRequest,
    processor: ProcessorService = Depends(get_processor_service),
    translator: TranslatorService = Depends(get_translator_service),
):
    """Dev mode endpoint. Accepts text, streams processing steps."""
    async def generate():
        try:
            detected_lang = body.lang
            if detected_lang == "auto":
                if any("\u0900" <= ch <= "\u097F" for ch in body.text):
                    detected_lang = "ne"
                else:
                    detected_lang = "en"
                yield json.dumps({"type": "step", "message": f"Auto-detected language: {detected_lang}"}) + "\n"

            yield json.dumps({
                "type": "asr",
                "transcript": body.text,
                "detected_lang": detected_lang
            }) + "\n"

            english_text = body.text
            if detected_lang == "ne":
                yield json.dumps({"type": "step", "message": "Translated Nepali to English for processing."}) + "\n"
                english_text = await translator.translate(body.text, "ne", "en")

            yield json.dumps({"type": "step", "message": "Processing query..."}) + "\n"
            result = await processor.process_query(
                text=body.text,
                source_lang=detected_lang,
                english_text=english_text,
            )
            answer_english = result["answer_english"]
            rag_sources = result.get("rag_sources", [])
            for s in result["steps"]:
                yield json.dumps({"type": "step", "message": s}) + "\n"

            yield json.dumps({
                "type": "process",
                "answer_english": answer_english,
                "rag_sources": rag_sources
            }) + "\n"

            if detected_lang == "ne":
                yield json.dumps({"type": "step", "message": "Translating response to Nepali."}) + "\n"
                final_text = await translator.translate(answer_english, "en", "ne")
            else:
                final_text = answer_english
                
            yield json.dumps({
                "type": "final_text",
                "final_text": final_text,
                "final_lang": detected_lang
            }) + "\n"

            yield json.dumps({"type": "done"}) + "\n"

        except Exception as e:
            logger.error(f"Dev process error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
