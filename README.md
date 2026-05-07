
# Nepali + English Voice Assistant (ASR • RAG • Translation • TTS)

This is a full-stack voice assistant that supports **Nepali** and **English**. It runs a lightweight local web app (FastAPI + a static frontend) and can optionally call **heavy ML models hosted remotely** on **Google Colab** or **Kaggle** via **ngrok**.

At a high level, Vani handles:

- **Audio → text** (ASR)
- **Intent & response generation** (weather/time + RAG Q&A)
- **English ⇄ Nepali translation**
- **Text → audio** (TTS)

If you don’t have GPU or models downloaded, you can still test everything in **Dev Mode (text-only)**.

---

## Table of Contents

- [Introduction](#introduction)
- [Demo](#demo)
- [Models & Datasets](#models--datasets)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Quickstart (Local)](#quickstart-local)
- [Dev Mode (Text Only)](#dev-mode-text-only)
- [Remote Models via Colab/Kaggle + ngrok](#remote-models-via-colabkaggle--ngrok)
- [Configuration (.env)](#configuration-env)
- [API Reference (Backend)](#api-reference-backend)
- [Notebooks](#notebooks)
- [Troubleshooting](#troubleshooting)

---

## Introduction

This repository contains a runnable “full app” experience:

- **Backend:** FastAPI service that orchestrates the ASR → processing → translation → TTS pipeline.
- **Frontend:** Single-page UI served by FastAPI (record audio, upload audio, dev-mode text input, and a streaming processing log).
- **Remote notebooks:** Jupyter notebooks to run GPU-heavy ASR and RAG/SLM pipelines in Colab/Kaggle and expose them publicly using ngrok.

The design goal is pragmatic: keep local setup light while still enabling strong model quality by offloading expensive inference to GPU runtimes.

---

## Demo



![Demo screenshot 1](https://github.com/Sangameeee/Nepali-audio-to-audio-pipeline/blob/main/images/audio_1.png)
![Demo screenshot 2](https://github.com/Sangameeee/Nepali-audio-to-audio-pipeline/blob/main/images/audio_2.png)


---

## Models & Datasets

### Try the Nepali ASR model (online demo)

- Hugging Face Space: https://huggingface.co/spaces/gam30/nepali-asr-indicconformer

### Download Nepali ASR model

- Model: https://huggingface.co/gam30/nepali-automatic-speech-recognition

### Datasets

- Test set (noisy): https://huggingface.co/datasets/gam30/nepali-asr-test-set-all-noisy
- Train/validation: https://huggingface.co/datasets/gam30/Nepali-asr-train-val

### Pipeline model links (Drive)

The pipeline folder also includes Drive links referenced by notebooks:

- LLM model: https://drive.google.com/file/d/1pJ947KCOmeM-zjFG5jTKUPan0QaNXz0R/view?usp=sharing
- ASR model: https://drive.google.com/file/d/10tIs7Xnq2QdGFQ82ZjXryFw8ttR3p6b9/view?usp=sharing

---

## Key Features

- **Nepali + English** interaction
- **Audio recording** in the browser + audio file upload
- **Streaming progress UI** (backend streams NDJSON steps)
- **Dev Mode (text-only)**: bypass ASR/TTS for faster iteration
- **Weather queries** (Open-Meteo; no API key required)
- **Time queries**
- **RAG Q&A** via remote Colab/Kaggle server (returns answer + sources)
- **Translation** EN↔NE via `deep-translator` (Google Translate wrapper)
- **TTS** using `gTTS` + `pydub` (optional online-TTS toggle in UI is currently a placeholder)

---

## Architecture

### Request flows

**Audio mode (UI default)**

1. Browser records/uploads audio
2. Backend converts to 16kHz mono WAV when possible
3. ASR runs:
	 - English audio: remote unified `/ask_audio` pipeline (ASR + RAG in one call)
	 - Nepali audio: remote `/transcribe` (Nepali ASR)
4. Query processor:
	 - Weather/time handled locally
	 - Q&A handled by remote RAG `/ask`
5. Translation (if needed)
6. TTS (gTTS)

**Dev Mode (text-only)**

1. Text is sent to the backend with `is_dev=true`
2. ASR and TTS are skipped
3. Processing, translation, and RAG behave the same

### Components

- Backend entry point: `backend/app/main.py`
- API router: `backend/app/routers/query.py`
- Services:
	- ASR: `backend/app/services/asr_service.py`
	- Processor (intent + RAG calls): `backend/app/services/processor.py`
	- Translator: `backend/app/services/translator.py`
	- TTS: `backend/app/services/tts_service.py`
	- Weather: `backend/app/services/weather_service.py`

---

## Repository Layout

```
.
├─ backend/                 # FastAPI backend
├─ frontend/                # Static UI (served by backend)
├─ notebook_files/          # Colab/Kaggle notebooks (ngrok endpoints)
├─ ASR-LLM-Pipeline/        # RAG + small language model (SLM) code
├─ run.sh                   # Convenience runner (uvicorn)
├─ run.txt                  # Local run instructions
└─ DEV_MODE_GUIDE.md        # Dev mode details
```

---

## Quickstart (Local)

### Prerequisites

- Python 3.10+
- `ffmpeg` (required by `pydub` for audio conversion)

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 1) Create & activate a virtualenv

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2) Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

### 3) Configure environment variables

The backend reads `backend/.env` automatically.

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` to set your ngrok URLs (see [Configuration (.env)](#configuration-env)).

### 4) Run the app

Option A — convenience script:

```bash
chmod +x run.sh
./run.sh
```

If you prefer a single checklist, see `run.txt`.

Option B — run uvicorn directly:

```bash
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

### 5) Open in the browser

- App UI: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

---

## Dev Mode (Text Only)

Dev Mode is designed for fast iteration without ASR/TTS.

- UI guide: [DEV_MODE_GUIDE.md](DEV_MODE_GUIDE.md)
- Under the hood it calls `/api/query` with `is_dev=true` (or `/api/dev_process`).

---

## Remote Models via Colab/Kaggle + ngrok

Vani supports running heavy inference remotely and calling it from your local machine.

### What you need to run remotely

Vani expects two remote servers:

1. **Nepali ASR server** (FastAPI + ngrok)
	 - Must provide: `GET /health`, `POST /transcribe` (supports `?decoder=ctc|rnnt`)
2. **Unified RAG/SLM (+ optional English ASR) server** (FastAPI + ngrok)
	 - Must provide: `GET /health`, `POST /ask` (text Q&A), `POST /ask_audio` (English audio → transcription + answer)

### Start the remote servers (notebooks)

- Nepali ASR on Kaggle: [notebook_files/nepali-asr-api-server-kaggle.ipynb](notebook_files/nepali-asr-api-server-kaggle.ipynb)
- Unified English ASR + RAG + SLM on Colab: [notebook_files/RAG_SLM_ASR_API_Server_v1.ipynb](notebook_files/RAG_SLM_ASR_API_Server_v1.ipynb)

Both notebooks:

- configure **ngrok auth token** (typically stored as a Secret called `ngrok_auth`)
- start uvicorn
- print a **public URL** like `https://xxxx.ngrok-free.app` (or `https://xxxx.ngrok-free.dev`)

### Point your local app at the new ngrok URLs

Update these fields in `backend/.env`:

- `ASR_COLAB_API_URL=<public_url_for_nepali_asr_server>`
- `RAG_COLAB_API_URL=<public_url_for_unified_rag_slm_server>`

Then restart your local backend.

---

## Configuration (.env)

Environment variables live in `backend/.env` (see `backend/.env.example`).

Most important variables for the “local app + remote models” workflow:

- `ASR_COLAB_API_URL`: Nepali ASR server base URL (ngrok)
- `ASR_DECODER`: `ctc` (fast) or `rnnt` (more accurate, slower)
- `RAG_COLAB_API_URL`: Unified RAG/SLM server base URL (ngrok)
- `RAG_MIN_COSINE`, `RAG_DAYS_FILTER`, `RAG_TOP_K`: retrieval thresholds forwarded to the remote RAG server

Other notable settings:

- `DEVICE`: `cpu` or `cuda` (used for local model integration if you enable it later)
- `WEATHER_PREFER_COUNTRY`: geocoding preference (default: Nepal)
- `MAX_UPLOAD_SIZE`: max audio upload size (bytes)

Full list (and defaults) is defined in `backend/app/config.py`.

---

## API Reference (Backend)

Base URL (local): `http://localhost:8000`

### Quick curl checks

Health:

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Dev Mode (text-only) — streams NDJSON (use `-N`):

```bash
curl -N -X POST http://localhost:8000/api/query \
	-F "text=What is the weather in Kathmandu?" \
	-F "lang=en" \
	-F "is_dev=true"
```

Audio mode — streams NDJSON:

```bash
curl -N -X POST http://localhost:8000/api/query \
	-F "audio=@/path/to/audio.wav" \
	-F "lang=ne" \
	-F "is_dev=false"
```

Core endpoints:

- `GET /api/health` — status + configured remote URLs
- `POST /api/query` — main streaming endpoint (audio or dev-mode text)
- `POST /api/dev_process` — streaming dev-mode endpoint (text-only)
- `POST /api/transcribe` — audio → transcript
- `POST /api/translate` — text translation
- `POST /api/synthesize` — text → audio

Colab-compatible helper endpoints:

- `POST /api/ask` — forwards text to the remote RAG `/ask`
- `POST /api/ask_audio` — accepts audio and forwards to remote `/ask_audio` (English audio path)

### Streaming format

`/api/query` and `/api/dev_process` stream **NDJSON** (`application/x-ndjson`) so the UI can show incremental status updates.

---

## Notebooks

- [notebook_files/nepali-asr-api-server-kaggle.ipynb](notebook_files/nepali-asr-api-server-kaggle.ipynb)
	- Runs a Nepali ASR FastAPI server on Kaggle GPU and exposes `/transcribe` via ngrok.
- [notebook_files/RAG_SLM_ASR_API_Server_v1.ipynb](notebook_files/RAG_SLM_ASR_API_Server_v1.ipynb)
	- Runs a unified server for `/ask` and `/ask_audio` (English ASR + RAG + SLM) on Colab GPU and exposes it via ngrok.
- [notebook_files/instruction_finetune_llm_sample.ipynb](notebook_files/instruction_finetune_llm_sample.ipynb)
	- Sample notebook for instruction-finetuning concepts (model training example / reference).

For deeper RAG/SLM internals, see:

- RAG docs: [ASR-LLM-Pipeline/RAG/README.md](ASR-LLM-Pipeline/RAG/README.md)
- SLM docs: [ASR-LLM-Pipeline/SLM/README.md](ASR-LLM-Pipeline/SLM/README.md)

---

## Troubleshooting

### “Cannot reach Colab server” / ASR fails

- Re-run the notebook and copy the new ngrok URL.
- Update `ASR_COLAB_API_URL` / `RAG_COLAB_API_URL` in `backend/.env`.
- Check health endpoints:
	- `<ASR_COLAB_API_URL>/health`
	- `<RAG_COLAB_API_URL>/health`

### Audio conversion issues

- Install ffmpeg (`sudo apt install -y ffmpeg`).
- If conversion fails, the backend will try to proceed with the original file.

### Translation or TTS not working

- `deep-translator` and `gTTS` rely on external services; ensure you have internet access.

### Running uvicorn from repo root fails with `ModuleNotFoundError: No module named 'app'`

- Run with `--app-dir backend` or run uvicorn from inside the `backend/` directory.

---

## Notes

- This project is currently configured for development convenience (CORS allows all origins; no auth).
- If you plan to deploy publicly, restrict CORS origins and add authentication.

