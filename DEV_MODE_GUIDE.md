# Dev Mode Guide — Voice Assistant

## What is Dev Mode?

Dev Mode is a **text-only testing mode** that bypasses the ASR (speech recognition) and TTS (text-to-speech) components. This is useful for:

- Testing the backend pipeline without loading heavy ML models
- Debugging intent detection and response generation
- Quick iteration on query processing logic
- Working on machines without GPU or without models downloaded

## How to Enable

1. Click the **"🔧 Dev Mode (Text Only)"** button in the top navigation bar.
2. The button turns indigo/blue when active.
3. The audio input section is replaced by a text input area.

## How to Use

1. **Enable Dev Mode** (click the toggle button).
2. **Select Language**: Choose English, Nepali, or Automatic from the dropdown.
3. **Enter Query**: Type your question in the text area.
4. **Submit**: Click "Process Query" or press `Ctrl+Enter`.
5. **View Results**: See the response in the right panel.

## Example Queries

### English Weather
```
What is the weather in Kathmandu?
```

### English Time
```
What time is it?
```

### Nepali Weather
```
काठमाडौंको मौसम कस्तो छ?
```

### Nepali News
```
नेपालको समाचार सुनाउनुस्
```

### General Query
```
Tell me about Nepal
```

## What Happens in Dev Mode

1. Your text is sent directly to the `/api/query` endpoint with `is_dev=true`.
2. The ASR step is skipped — your text is used as the "transcript".
3. If language is "auto", Devanagari characters are detected for Nepali.
4. Intent detection and response generation work normally.
5. Translation works normally (EN↔NE).
6. TTS synthesis is skipped — only text response is returned.
7. The processing log shows all steps for debugging.

## API Endpoint

Dev mode uses the same `/api/query` endpoint:

```bash
curl -X POST http://localhost:8000/api/query \
  -F "text=What is the weather in Kathmandu?" \
  -F "lang=en" \
  -F "is_dev=true"
```

Or use the dedicated `/api/dev_process` endpoint:

```bash
curl -X POST http://localhost:8000/api/dev_process \
  -H "Content-Type: application/json" \
  -d '{"text": "What is the weather?", "lang": "en", "is_dev": true}'
```

## Switching Back to Audio Mode

Click the "🔧 Dev Mode ON" button again to return to audio input mode.
