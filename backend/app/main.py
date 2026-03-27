# ==============================================================================
# Vani - FastAPI Main Application
# File: backend/app/main.py
#
# Purpose:
#   Entry point for the Vani backend. Sets up:
#     - FastAPI app instance with metadata
#     - CORS middleware (allows frontend requests)
#     - Static file serving (frontend HTML/CSS/JS)
#     - Application lifespan (startup/shutdown for model loading/unloading)
#     - Router registration
#
# How to run:
#   cd vani/backend
#   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
#
# Architecture:
#   ┌─────────────┐     ┌──────────────┐
#   │   Frontend   │────▶│  FastAPI App  │
#   │  (static)    │     │   main.py     │
#   └─────────────┘     └──────┬───────┘
#                              │
#                    ┌─────────┼─────────┐
#                    ▼         ▼         ▼
#              ┌──────────┐ ┌──────┐ ┌──────┐
#              │ ASR Svc  │ │Proc. │ │ TTS  │
#              │          │ │ Svc  │ │ Svc  │
#              └──────────┘ └──┬───┘ └──────┘
#                              │
#                    ┌─────────┼─────────┐
#                    ▼         ▼         ▼
#              ┌──────────┐ ┌──────┐ ┌──────┐
#              │ Weather  │ │ RAG  │ │Trans │
#              │  API     │ │ LLM  │ │lator │
#              └──────────┘ └──────┘ └──────┘
#
# Lifespan:
#   On startup: All services are instantiated and optionally models are loaded.
#   On shutdown: All services are cleaned up and resources released.
#   Services are stored in app.state for access via dependency injection.
# ==============================================================================

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import query
from app.services.asr_service import ASRService
from app.services.processor import ProcessorService
from app.services.translator import TranslatorService
from app.services.tts_service import TTSService
from app.services.weather_service import WeatherService

# ── Logging Setup ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("vani.main")


# ── Application Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    STARTUP:
      1. Load configuration.
      2. Create temp directories.
      3. Instantiate all services (ASR, Processor, Translator, TTS).
      4. Optionally pre-load models (currently mock mode, so instant).
      5. Store services in app.state for dependency injection.

    SHUTDOWN:
      1. Clean up all services (release models, free VRAM).
      2. Clean up temp files.

    To switch from lazy to eager model loading:
      - Call service._load_xxx_model() methods here during startup.
      - This will increase startup time but ensure models are ready.

    To manage VRAM (load one model at a time):
      - Load ASR model, transcribe, unload ASR model.
      - Load TTS model, synthesize, unload TTS model.
      - This is slower but uses less memory.
      - Implement this in the router by calling service.cleanup() between steps.
    """
    settings = get_settings()

    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} v{settings.APP_VERSION} - Starting Up")
    logger.info(f"  Device: {settings.DEVICE}")
    logger.info(f"  Debug: {settings.DEBUG}")
    logger.info("=" * 60)

    # Create necessary directories
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    os.makedirs(settings.TTS_OUTPUT_DIR, exist_ok=True)

    # ── Initialize Services ──────────────────────────────────────────
    logger.info("Initializing services...")

    app.state.asr_service = ASRService(settings)
    logger.info("  ✓ ASR Service ready")

    app.state.translator_service = TranslatorService(settings)
    logger.info("  ✓ Translator Service ready")

    app.state.weather_service = WeatherService(
        prefer_country=settings.WEATHER_PREFER_COUNTRY
    )
    logger.info("  ✓ Weather Service ready (Open-Meteo)")

    app.state.processor_service = ProcessorService(settings, app.state.weather_service)
    logger.info("  ✓ Processor Service ready")

    app.state.tts_service = TTSService(settings)
    logger.info("  ✓ TTS Service ready")

    # ── Optional: Eager Model Loading ────────────────────────────────
    # Uncomment these lines to pre-load models at startup.
    # This increases startup time but reduces first-request latency.
    #
    # logger.info("Pre-loading models...")
    # app.state.asr_service._load_english_model()
    # app.state.asr_service._load_nepali_model()
    # app.state.asr_service._load_language_detector()
    # app.state.translator_service._load_en_to_ne()
    # app.state.translator_service._load_ne_to_en()
    # app.state.tts_service._load_model()
    # logger.info("All models pre-loaded.")

    logger.info("=" * 60)
    logger.info(f"  {settings.APP_NAME} is ready! http://localhost:8000")
    logger.info("=" * 60)

    yield  # ── Application is running ──

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down services...")

    app.state.asr_service.cleanup()
    app.state.translator_service.cleanup()
    await app.state.processor_service.cleanup()
    await app.state.weather_service.cleanup()
    app.state.tts_service.cleanup()

    # Clean up temp files
    from app.services.utils import cleanup_temp_files
    cleanup_temp_files(settings.TEMP_DIR, max_age_seconds=0)

    logger.info("Vani shutdown complete.")


# ── Create FastAPI App ───────────────────────────────────────────────────

app = FastAPI(
    title="Vani - Voice Assistant",
    description=(
        "Voice Assistant for Nepali + English. "
        "Accepts audio or text input, processes through ASR → Intent Detection → "
        "Response Generation → Translation → TTS pipeline."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS Middleware ──────────────────────────────────────────────────────
# Allow frontend to communicate with backend.
# In production, restrict origins to your actual domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ────────────────────────────────────────────────────
app.include_router(query.router)

# ── Static File Serving ─────────────────────────────────────────────────
# Serve the frontend from the /frontend directory.
# The frontend is a single-page app with index.html, style.css, and app.js.
settings = get_settings()
frontend_dir = settings.STATIC_DIR

if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# ── Root Route: Serve Frontend ──────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    """
    Serve the frontend index.html at the root URL.
    All frontend assets (CSS, JS) are loaded from /static/.
    """
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Vani API is running. Frontend not found at " + frontend_dir}


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon (optional)."""
    favicon_path = os.path.join(frontend_dir, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))
