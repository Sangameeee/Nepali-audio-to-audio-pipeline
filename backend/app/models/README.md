# Models Directory

This directory is for storing ML model checkpoints. It is **gitignored** to avoid committing large files.

## Directory Structure

```
models/
├── asr/
│   ├── english/          # NVIDIA NeMo English ASR
│   │   └── nemo_conformer.nemo
│   └── nepali/           # ai4bharat/indic-conformer-600m-multilingual
│       ├── config.json
│       ├── pytorch_model.bin
│       ├── preprocessor_config.json
│       └── tokenizer.json
├── tts/
│   ├── outputs/          # Generated TTS audio files (temp)
│   └── xtts_v2/          # XTTS-v2 model files (auto-downloaded)
└── rag/
    └── faiss_index/      # FAISS vector store index
```

## Download Instructions

### English ASR (NeMo)

```bash
# Option 1: From NVIDIA NGC
pip install nemo_toolkit[asr]
python -c "
import nemo.collections.asr as nemo_asr
model = nemo_asr.models.EncDecRNNTBPEModel.from_pretrained('stt_en_conformer_transducer_large')
model.save_to('models/asr/english/nemo_conformer.nemo')
"

# Option 2: Direct download from NGC catalog
# Visit: https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo/models
```

### Nepali ASR (Indic-Conformer)

```bash
git lfs install
git clone https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual models/asr/nepali
```

### TTS (XTTS-v2)

```bash
# Auto-downloads on first use, or pre-download:
pip install TTS
python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

### Translation Models

```bash
# Auto-download from HuggingFace on first use
pip install transformers sentencepiece
python -c "
from transformers import MarianMTModel, MarianTokenizer
MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-en-ne')
MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-en-ne')
MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-ne-en')
MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-ne-en')
"
```
