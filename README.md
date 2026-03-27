# Voice Assistant for Nepali + English

Welcome to **Voice Assistant**, a full-stack web application that accepts audio or text input, processes it through a pipeline of **language detection → ASR → intent detection → response generation → translation → TTS**, and returns an audio response in the appropriate language.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Browser)                       │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐ │
│  │ Record   │  │ Upload   │  │  Dev    │  │  Response    │ │
│  │ Audio    │  │ Audio    │  │  Input  │  │  Display     │ │
│  └────┬─────┘  └────┬─────┘  └────┬────┘  └──────────────┘ │
│       │              │             │                         │
└───────┼──────────────┼─────────────┼─────────────────────────┘
        │              │             │
        ▼              ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (:8000)                      │
│                                                              │
│  /api/query ─────────────────────────────────────────────►  │
│       │                                                      │
│       ├─► ASR Service ──────► Transcript                     │
│       │   ├── English (NeMo Conformer)                       │
│       │   ├── Nepali (Indic-Conformer 600M)                  │
│       │   └── Auto (Language Detection)                      │
│       │                                                      │
│       ├─► Translator Service ──► EN↔NE Translation           │
│       │   ├── Helsinki-NLP/opus-mt-en-ne                     │
│       │   └── Helsinki-NLP/opus-mt-ne-en                     │
│       │                                                      │
│       ├─► Processor Service ──► Intent + Response            │
│       │   ├── Weather (OpenWeatherMap API)                   │
│       │   ├── Time (Python datetime)                         │
│       │   ├── News (RAG + LLM placeholder)                   │
│       │   └── General (LLM fallback placeholder)             │
│       │                                                      │
│       └─► TTS Service ──────► Audio Response                 │
│           └── Coqui XTTS-v2                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Dual Language Support**: English and Nepali (with automatic detection)
- **Audio Input**: Live recording via browser microphone or file upload
- **Dev Mode**: Text-only mode for testing without ASR/TTS models
- **Intent Detection**: Weather queries, time, news, general knowledge
- **Translation Pipeline**: Automatic EN↔NE translation via Helsinki-NLP
- **Text-to-Speech**: Coqui XTTS-v2 for multilingual speech synthesis
- **Mock Mode**: Fully functional with mock responses when models aren't loaded
- **Clean UI**: Dark theme with Tailwind CSS, responsive design, waveform visualization

---

## Prerequisites

- **Python 3.9+** (3.11 recommended)
- **FFmpeg** (for audio format conversion)
  ```bash
  # Ubuntu/Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg
  ```
- **Node.js** (not required — frontend is vanilla JS with Tailwind CDN)

---

## Setup & Installation

### 1. Clone and Navigate

```bash
cd vani
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys and model paths
```

### 5. Run the Server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open in Browser

Visit: **http://localhost:8000**

---

## Project Structure

```
vani/
├── backend/
│   ├── app/
│   │   ├── __init__.py              # Package init
│   │   ├── main.py                  # FastAPI app, CORS, static files, lifespan
│   │   ├── config.py                # Pydantic Settings (paths, API keys, device)
│   │   ├── schemas.py               # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── query.py             # All /api endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── asr_service.py       # English NeMo + Nepali Indic-Conformer
│   │   │   ├── processor.py         # Weather, news, RAG/LLM fallback
│   │   │   ├── translator.py        # EN↔NE translation
│   │   │   ├── tts_service.py       # XTTS-v2 TTS
│   │   │   └── utils.py             # Audio handling, temp files, base64
│   │   └── models/                  # Empty – for model integration docs
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html                   # Single-page app UI
│   ├── style.css                    # Custom styles
│   └── app.js                       # Frontend logic
├── models/                          # Model checkpoints (gitignored)
│   ├── asr/
│   │   ├── english/                 # NeMo checkpoints go here
│   │   └── nepali/                  # Indic-Conformer files go here
│   ├── tts/                         # XTTS-v2 files
│   └── rag/                         # RAG embeddings
├── data/
│   └── news/                        # News documents for RAG
├── README.md
├── DEV_MODE_GUIDE.md
└── run.sh                           # Convenience script
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check, model status |
| POST | `/api/query` | Main pipeline (audio/text → response) |
| POST | `/api/transcribe` | Audio → text only |
| POST | `/api/synthesize` | Text → audio only |
| POST | `/api/dev_process` | Dev mode (text → text) |

### `/api/query` Parameters

**Audio Mode** (multipart form data):
- `audio`: Audio file (WAV, MP3, M4A, OGG, FLAC, WEBM)
- `lang`: `"en"`, `"ne"`, or `"auto"`
- `is_dev`: `"false"`

**Dev Mode** (multipart form data):
- `text`: Query text string
- `lang`: `"en"`, `"ne"`, or `"auto"`
- `is_dev`: `"true"`

### Response Format

```json
{
  "transcript": "What is the weather in Kathmandu?",
  "detected_lang": "en",
  "answer_english": "Weather in Kathmandu: 22°C, partly cloudy...",
  "final_text": "Weather in Kathmandu: 22°C, partly cloudy...",
  "final_lang": "en",
  "audio_base64": "data:audio/wav;base64,...",
  "processing_steps": [
    "Dev mode: Using text input (lang=en)",
    "Detected intent: weather",
    "Fetched weather data from OpenWeatherMap API.",
    "✓ Pipeline complete."
  ],
  "error": null
}
```

---

## Model Integration

The app runs in **mock mode** by default (no ML models needed). To integrate real models:

### English ASR (NVIDIA NeMo)

1. Install: `pip install nemo_toolkit[asr]`
2. Download: `stt_en_conformer_transducer_large` from NVIDIA NGC
3. Place at: `models/asr/english/nemo_conformer.nemo`
4. Uncomment code in `backend/app/services/asr_service.py` → `_load_english_model()`

### Nepali ASR (Indic-Conformer 600M)

1. Install: `pip install transformers speechbrain`
2. Download:
   ```bash
   git lfs install
   git clone https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual models/asr/nepali
   ```
3. Uncomment code in `asr_service.py` → `_load_nepali_model()`

### Translation (Helsinki-NLP)

1. Install: `pip install transformers sentencepiece`
2. Models auto-download from HuggingFace on first use
3. Uncomment code in `translator.py` → `_load_en_to_ne()` / `_load_ne_to_en()`

### TTS (Coqui XTTS-v2)

1. Install: `pip install TTS`
2. Model auto-downloads on first use (~1.8GB)
3. Prepare a reference WAV file for voice cloning
4. Uncomment code in `tts_service.py` → `_load_model()`

### RAG + LLM (for News)

1. Install: `pip install langchain faiss-cpu sentence-transformers`
2. Place news documents in `data/news/`
3. Follow the TODO comments in `processor.py` → `_handle_news()`

### Weather API

1. Get a free API key at [OpenWeatherMap](https://openweathermap.org/api)
2. Set `OPENWEATHERMAP_API_KEY=your_key` in `.env`

---

## Dev Mode

Toggle "Dev Mode" in the top navbar to test without ASR/TTS:

- Audio input is replaced by a text field
- Enter queries directly (English or Nepali)
- TTS output is skipped; only text responses are shown
- Useful for testing intent detection, weather API, etc.

**Keyboard shortcut**: `Ctrl+Enter` to submit in dev mode.

See [DEV_MODE_GUIDE.md](DEV_MODE_GUIDE.md) for more details.

---

## Adding New Features

### New Language

1. Add ASR model integration in `asr_service.py`
2. Add translation pairs in `translator.py`
3. Update language dropdown in `frontend/index.html`
4. Update `LANG_DETECT_MODEL` configuration if needed

### New Intent Handler

1. Add keywords to `processor.py` (e.g., `SPORTS_KEYWORDS`)
2. Create handler method `_handle_sports()`
3. Add routing logic in `_detect_intent()` and `process_query()`

### New TTS Voice

1. Add reference WAV to `models/tts/`
2. Update `TTS_REFERENCE_WAV` in `.env`
3. Or add multiple voice options with a selection dropdown

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: pydantic_settings` | `pip install pydantic-settings` |
| Audio conversion fails | Install FFmpeg: `sudo apt install ffmpeg` |
| CUDA out of memory | Set `DEVICE=cpu` in `.env` or reduce model batch size |
| Frontend not loading | Ensure server is running on port 8000, check `/frontend/` exists |
| Weather API mock data | Set `OPENWEATHERMAP_API_KEY` in `.env` |
| Recording not working | Allow microphone access in browser, use HTTPS or localhost |

---

## Future Roadmap

- [ ] WebSocket streaming for real-time ASR
- [ ] Multi-turn conversation support
- [ ] User authentication
- [ ] Docker deployment
- [ ] Streaming TTS response
- [ ] Custom wake word detection
- [ ] Mobile-responsive PWA
- [ ] Batch processing mode

---

## License

MIT License — See LICENSE file for details.
