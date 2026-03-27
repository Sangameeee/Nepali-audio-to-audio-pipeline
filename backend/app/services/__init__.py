# ==============================================================================
# Vani - Services Package
#
# This package contains all service modules that handle the core logic:
#   - asr_service.py    : Automatic Speech Recognition (English NeMo + Nepali Indic-Conformer)
#   - processor.py      : Query processing (weather, news, RAG/LLM fallback)
#   - translator.py     : Translation between English and Nepali (NLLB / Helsinki-NLP)
#   - tts_service.py    : Text-to-Speech synthesis (Coqui XTTS-v2)
#   - utils.py          : Audio handling, temp files, base64 encoding
#
# Services are designed with dependency injection in mind. They are loaded
# once at application startup (via FastAPI lifespan) and injected into
# route handlers via FastAPI's Depends() mechanism.
# ==============================================================================
