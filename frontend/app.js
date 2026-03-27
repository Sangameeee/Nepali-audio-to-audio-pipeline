/*
 * ==============================================================================
 * Voice Assistant - Frontend Application Logic
 * File: frontend/app.js
 *
 * All frontend logic for the voice assistant.
 * Classical white theme – no Tailwind dependency.
 * ==============================================================================
 */

// ══════════════════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════════════════

const state = {
    isDevMode: false,
    useOnlineTts: false,
    isRecording: false,
    isPlaying: false,
    isLoading: false,
    autoVoiceOutput: false,
    mediaRecorder: null,
    audioChunks: [],
    audioBlob: null,
    uploadedFile: null,
    audioContext: null,
    analyser: null,
    animationFrame: null,
};

const API_BASE = '';

function normalizeAssistantText(text) {
    if (!text || typeof text !== 'string') return text;
    return text.replace(/^\s*response\s*:\s*/i, '').trim();
}

function toggleAutoVoice() {
    state.autoVoiceOutput = !state.autoVoiceOutput;
    localStorage.setItem('voice_assistant.autoVoiceOutput', state.autoVoiceOutput ? '1' : '0');

    const autoBtn = document.getElementById('autoVoiceBtn');
    if (state.autoVoiceOutput) {
        autoBtn.classList.add('active');
        autoBtn.textContent = 'Auto Voice ON';
        addStatusLog('Auto voice output enabled.', 'info');
    } else {
        autoBtn.classList.remove('active');
        autoBtn.textContent = 'Auto Voice OFF';
        addStatusLog('Auto voice output disabled.', 'info');
    }
}

async function tryAutoPlayAudio(audioPlayer) {
    if (!state.autoVoiceOutput) return;

    try {
        audioPlayer.currentTime = 0;
        await audioPlayer.play();
        addStatusLog('Auto-playing audio response.', 'success');
    } catch (error) {
        addStatusLog('Auto-play blocked by browser. Use the audio controls to play.', 'warning');
    }
}

function toggleOnlineTts() {
    state.useOnlineTts = !state.useOnlineTts;
    localStorage.setItem('voice_assistant.useOnlineTts', state.useOnlineTts ? '1' : '0');

    const btn = document.getElementById('onlineTtsBtn');
    if (state.useOnlineTts) {
        btn.classList.add('active');
        btn.textContent = 'Online TTS ON';
        addStatusLog('Online TTS enabled.', 'info');
    } else {
        btn.classList.remove('active');
        btn.textContent = 'Online TTS OFF';
        addStatusLog('Online TTS disabled (using gTTS).', 'info');
    }
}

// ══════════════════════════════════════════════════════════════════════════
// DEV MODE
// ══════════════════════════════════════════════════════════════════════════

function toggleDevMode() {
    state.isDevMode = !state.isDevMode;

    const devBtn = document.getElementById('devModeBtn');
    const audioSection = document.getElementById('audioSection');
    const devSection = document.getElementById('devSection');
    const translateSection = document.getElementById('translateSection');
    const submitAudioBtn = document.getElementById('submitAudioBtn');

    if (state.isDevMode) {
        devBtn.classList.add('active');
        devBtn.innerHTML = '&#9881; Dev Mode ON';
        audioSection.classList.add('hidden');
        submitAudioBtn.classList.add('hidden');
        devSection.classList.remove('hidden');
        translateSection.classList.remove('hidden');
    } else {
        devBtn.classList.remove('active');
        devBtn.innerHTML = '&#9881; Dev Mode';
        audioSection.classList.remove('hidden');
        devSection.classList.add('hidden');
        translateSection.classList.add('hidden');
    }

    addStatusLog('Dev mode ' + (state.isDevMode ? 'enabled' : 'disabled') + '.', 'info');
}

// ══════════════════════════════════════════════════════════════════════════
// AUDIO RECORDING
// ══════════════════════════════════════════════════════════════════════════

async function toggleRecording() {
    if (state.isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: 16000 }
        });

        state.audioChunks = [];
        state.uploadedFile = null;

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : 'audio/webm';

        state.mediaRecorder = new MediaRecorder(stream, { mimeType });

        state.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                state.audioChunks.push(event.data);
            }
        };

        state.mediaRecorder.onstop = () => {
            state.audioBlob = new Blob(state.audioChunks, { type: mimeType });
            stream.getTracks().forEach(track => track.stop());
            addStatusLog(`Recording complete (${(state.audioBlob.size / 1024).toFixed(1)} KB).`, 'success');
            document.getElementById('submitAudioBtn').classList.remove('hidden');

            // Show input audio playback
            const inputPlayer = document.getElementById('inputAudioPlayer');
            const inputSection = document.getElementById('inputAudioSection');
            inputPlayer.src = URL.createObjectURL(state.audioBlob);
            inputSection.classList.remove('hidden');
        };

        state.mediaRecorder.start(100);
        state.isRecording = true;

        const recordBtn = document.getElementById('recordBtn');
        recordBtn.classList.add('recording-active');
        document.getElementById('recordText').textContent = 'Stop Recording';
        document.getElementById('waveformContainer').classList.remove('hidden');

        startWaveformVisualization(stream);
        addStatusLog('Recording started. Speak now...', 'info');
        document.getElementById('fileInfo').classList.add('hidden');

    } catch (error) {
        console.error('Recording error:', error);
        addStatusLog(`Microphone error: ${error.message}`, 'error');
    }
}

function stopRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;

        const recordBtn = document.getElementById('recordBtn');
        recordBtn.classList.remove('recording-active');
        document.getElementById('recordText').textContent = 'Start Recording';

        if (state.animationFrame) {
            cancelAnimationFrame(state.animationFrame);
            state.animationFrame = null;
        }
    }
}

function startWaveformVisualization(stream) {
    state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = state.audioContext.createMediaStreamSource(stream);
    state.analyser = state.audioContext.createAnalyser();
    state.analyser.fftSize = 256;
    source.connect(state.analyser);

    const canvas = document.getElementById('waveformCanvas');
    const ctx = canvas.getContext('2d');
    const bufferLength = state.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        state.animationFrame = requestAnimationFrame(draw);
        state.analyser.getByteFrequencyData(dataArray);

        ctx.fillStyle = '#f5f3ef';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const barWidth = (canvas.width / bufferLength) * 2.5;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = (dataArray[i] / 255) * canvas.height;
            const gradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
            gradient.addColorStop(0, '#4a4e8a');
            gradient.addColorStop(1, '#7a7eb8');
            ctx.fillStyle = gradient;
            ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
            x += barWidth;
        }
    }

    draw();
}

// ══════════════════════════════════════════════════════════════════════════
// FILE UPLOAD
// ══════════════════════════════════════════════════════════════════════════

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const allowedTypes = ['.wav', '.mp3', '.m4a', '.ogg', '.flac', '.webm'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowedTypes.includes(ext)) {
        addStatusLog(`Unsupported format: ${ext}. Use: ${allowedTypes.join(', ')}`, 'error');
        return;
    }

    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
        addStatusLog('File too large. Maximum: 50MB.', 'error');
        return;
    }

    state.uploadedFile = file;
    state.audioBlob = null;

    const fileInfo = document.getElementById('fileInfo');
    fileInfo.classList.remove('hidden');
    document.getElementById('fileName').textContent =
        `\u{1F4C1} ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

    document.getElementById('submitAudioBtn').classList.remove('hidden');

    // Show input audio playback for uploaded file
    const inputPlayer = document.getElementById('inputAudioPlayer');
    const inputSection = document.getElementById('inputAudioSection');
    inputPlayer.src = URL.createObjectURL(file);
    inputSection.classList.remove('hidden');

    addStatusLog(`File selected: ${file.name}`, 'info');
}

// ══════════════════════════════════════════════════════════════════════════
// API COMMUNICATION
// ══════════════════════════════════════════════════════════════════════════

async function submitAudioQuery() {
    const audioSource = state.audioBlob || state.uploadedFile;
    if (!audioSource) {
        addStatusLog('No audio available. Record or upload first.', 'error');
        return;
    }

    if (state.isLoading) return;
    state.isLoading = true;

    const lang = document.getElementById('langSelect').value;
    clearResults();
    addStatusLog('Sending audio to asr...', 'info');

    try {
        const formData = new FormData();

        if (state.audioBlob) {
            formData.append('audio', state.audioBlob, 'recording.webm');
        } else if (state.uploadedFile) {
            formData.append('audio', state.uploadedFile);
        }

        formData.append('lang', lang);
        formData.append('is_dev', 'false');
        formData.append('use_online_tts', state.useOnlineTts);

        const response = await fetch(`${API_BASE}/api/query`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            // Attempt to parse json error, if not possible use text
            let errMsg = `Server error: ${response.status}`;
            try {
                const error = await response.json();
                errMsg = error.detail || errMsg;
            } catch (e) {}
            throw new Error(errMsg);
        }

        await processNdjsonStream(response);

    } catch (error) {
        console.error('Submit error:', error);
        addStatusLog(`Error: ${error.message}`, 'error');
        showError(error.message);
    } finally {
        state.isLoading = false;
    }
}

async function submitDevQuery() {
    const text = document.getElementById('devTextInput').value.trim();
    if (!text) {
        addStatusLog('Please enter a query text.', 'error');
        return;
    }

    if (state.isLoading) return;
    state.isLoading = true;

    const lang = document.getElementById('langSelect').value;
    clearResults();
    addStatusLog('Processing text query...', 'info');

    const btn = document.getElementById('devSubmitBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-dots">Processing</span>';

    try {
        const formData = new FormData();
        formData.append('text', text);
        formData.append('lang', lang);
        formData.append('is_dev', 'true');
        formData.append('use_online_tts', state.useOnlineTts);

        const response = await fetch(`${API_BASE}/api/query`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            let errMsg = `Server error: ${response.status}`;
            try {
                const error = await response.json();
                errMsg = error.detail || errMsg;
            } catch (e) {}
            throw new Error(errMsg);
        }

        await processNdjsonStream(response);

    } catch (error) {
        console.error('Dev query error:', error);
        addStatusLog(`Error: ${error.message}`, 'error');
        showError(error.message);
    } finally {
        state.isLoading = false;
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6"/>
            </svg>
            Process Query`;
    }
}

// ══════════════════════════════════════════════════════════════════════════
// TRANSLATION
// ══════════════════════════════════════════════════════════════════════════

async function submitTranslation() {
    const text = document.getElementById('translateInput').value.trim();
    if (!text) {
        addStatusLog('Please enter text to translate.', 'error');
        return;
    }

    const srcLang = document.getElementById('srcLangSelect').value;
    const tgtLang = document.getElementById('tgtLangSelect').value;

    if (srcLang === tgtLang) {
        addStatusLog('Source and target languages are the same.', 'warning');
        return;
    }

    const btn = document.getElementById('translateBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-dots">Translating</span>';
    addStatusLog(`Translating ${srcLang} → ${tgtLang}...`, 'info');

    try {
        const response = await fetch(`${API_BASE}/api/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                source_lang: srcLang,
                target_lang: tgtLang,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Server error: ${response.status}`);
        }

        const data = await response.json();

        const resultSection = document.getElementById('translateResult');
        resultSection.classList.remove('hidden');
        document.getElementById('translateResultText').textContent = data.translated_text;

        addStatusLog(`Translation complete (${srcLang} → ${tgtLang}).`, 'success');

    } catch (error) {
        console.error('Translation error:', error);
        addStatusLog(`Translation error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"/>
            </svg>
            Translate`;
    }
}

// ══════════════════════════════════════════════════════════════════════════
// RESPONSE DISPLAY
// ══════════════════════════════════════════════════════════════════════════

async function processNdjsonStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        buffer = lines.pop(); // Keep partial line in buffer

        for (const line of lines) {
            if (line.trim() === '') continue;
            try {
                const data = JSON.parse(line);
                handleStreamChunk(data);
            } catch (err) {
                console.error("Failed to parse stream chunk JSON:", line, err);
            }
        }
    }
    
    if (buffer.trim() !== '') {
        try {
            const data = JSON.parse(buffer);
            handleStreamChunk(data);
        } catch (err) {
            console.error("Failed to parse final stream chunk JSON:", buffer, err);
        }
    }
}

function handleStreamChunk(data) {
    if (data.type === 'step') {
        addStatusLog(data.message, 'success');
    } else if (data.type === 'input_audio') {
        if (data.input_audio_base64) {
            const inputSection = document.getElementById('inputAudioSection');
            const inputPlayer = document.getElementById('inputAudioPlayer');
            inputSection.classList.remove('hidden');
            inputPlayer.src = data.input_audio_base64;
        }
    } else if (data.type === 'asr') {
        const transcriptEl = document.getElementById('transcriptText');
        if (data.transcript) {
            transcriptEl.textContent = data.transcript;
            transcriptEl.classList.remove('placeholder-text');
        }
        const langBadge = document.getElementById('detectedLangBadge');
        if (data.detected_lang) {
            langBadge.textContent = data.detected_lang === 'ne' ? 'Nepali' : 'English';
            langBadge.classList.remove('hidden');
        }
    } else if (data.type === 'process') {
        if (data.answer_english) {
            document.getElementById('englishAnswerSection').classList.remove('hidden');
            document.getElementById('englishAnswerText').textContent = normalizeAssistantText(data.answer_english);
        }
        if (data.rag_sources && data.rag_sources.length > 0) {
            displayRagSources(data.rag_sources);
        }
    } else if (data.type === 'final_text') {
        const responseEl = document.getElementById('responseText');
        if (data.final_text) {
            responseEl.textContent = normalizeAssistantText(data.final_text);
            responseEl.classList.remove('placeholder-text');
        }
        const respLangBadge = document.getElementById('responseLangBadge');
        if (data.final_lang) {
            respLangBadge.textContent = data.final_lang === 'ne' ? 'नेपाली' : 'English';
            respLangBadge.classList.remove('hidden');
        }
    } else if (data.type === 'audio') {
        if (data.audio_base64) {
            const playerSection = document.getElementById('audioPlayerSection');
            const audioPlayer = document.getElementById('audioPlayer');
            playerSection.classList.remove('hidden');
            audioPlayer.src = data.audio_base64;
            if (state.autoVoiceOutput) {
                addStatusLog('Audio response ready. Auto-play is enabled.', 'success');
                void tryAutoPlayAudio(audioPlayer);
            } else {
                addStatusLog('Audio response ready for playback.', 'success');
            }
        }
    } else if (data.type === 'error') {
        showError(data.error);
        addStatusLog('Pipeline error: ' + data.error, 'error');
    } else if (data.type === 'done') {
        addStatusLog('\u2713 Pipeline complete.', 'success');
    }
}

function displayRagSources(sources) {
    const sourcesSection = document.getElementById('ragSourcesSection');
    const sourcesList = document.getElementById('ragSourcesList');
    const sourcesCount = document.getElementById('sourcesCount');

    sourcesSection.classList.remove('hidden');
    sourcesCount.textContent = sources.length;
    sourcesList.innerHTML = '';

    sources.forEach(s => {
        const item = document.createElement('div');
        item.className = 'rag-source-item';
        item.innerHTML = `
            <div class="rag-source-rank">#${s.rank || '?'}</div>
            <div class="rag-source-content">
                <a href="${s.url || '#'}" target="_blank" class="rag-source-title">${s.title || 'Untitled'}</a>
                <div class="rag-source-meta">
                    <span>${s.date || ''}</span>
                    ${s.rerank_score ? `<span>Relevance: ${(s.rerank_score * 100).toFixed(0)}%</span>` : ''}
                </div>
            </div>
        `;
        sourcesList.appendChild(item);
    });
}

function toggleSources() {
    const list = document.getElementById('ragSourcesList');
    list.classList.toggle('collapsed');
}

function clearResults() {
    document.getElementById('transcriptText').innerHTML =
        '<span class="placeholder-text">Processing...</span>';
    document.getElementById('detectedLangBadge').classList.add('hidden');

    document.getElementById('responseText').innerHTML =
        '<span class="placeholder-text">Waiting for response...</span>';
    document.getElementById('responseLangBadge').classList.add('hidden');

    document.getElementById('englishAnswerSection').classList.add('hidden');
    document.getElementById('audioPlayerSection').classList.add('hidden');
    document.getElementById('ragSourcesSection').classList.add('hidden');
    document.getElementById('errorSection').classList.add('hidden');

    document.getElementById('statusLog').innerHTML = '';
}

function showError(message) {
    const errorSection = document.getElementById('errorSection');
    errorSection.classList.remove('hidden');
    document.getElementById('errorText').textContent = message;
}

// ══════════════════════════════════════════════════════════════════════════
// STATUS LOG
// ══════════════════════════════════════════════════════════════════════════

function addStatusLog(message, type = 'info') {
    const log = document.getElementById('statusLog');
    const entry = document.createElement('div');
    entry.className = 'status-entry';

    const icons = {
        info: '\u25CF',
        success: '\u2713',
        error: '\u2717',
        warning: '\u26A0',
    };

    const icon = icons[type] || icons.info;
    const time = new Date().toLocaleTimeString('en-US', {
        hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
    });

    entry.innerHTML = `
        <span class="status-icon ${type}">${icon}</span>
        <span class="status-time">${time}</span>
        <span class="status-msg">${message}</span>
    `;

    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

// ══════════════════════════════════════════════════════════════════════════
// UTILITY
// ══════════════════════════════════════════════════════════════════════════

async function copyResponse() {
    const responseText = document.getElementById('responseText').textContent;
    if (!responseText || responseText.includes('No response yet')) {
        return;
    }

    try {
        await navigator.clipboard.writeText(responseText);
        addStatusLog('Response copied to clipboard.', 'info');
    } catch (error) {
        const textArea = document.createElement('textarea');
        textArea.value = responseText;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        addStatusLog('Response copied to clipboard.', 'info');
    }
}

// ══════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
    const autoBtn = document.getElementById('autoVoiceBtn');
    const savedAutoVoice = localStorage.getItem('voice_assistant.autoVoiceOutput');
    state.autoVoiceOutput = savedAutoVoice === '1';
    if (state.autoVoiceOutput) {
        autoBtn.classList.add('active');
        autoBtn.textContent = 'Auto Voice ON';
    } else {
        autoBtn.classList.remove('active');
        autoBtn.textContent = 'Auto Voice OFF';
    }

    const onlineBtn = document.getElementById('onlineTtsBtn');
    const savedOnlineTts = localStorage.getItem('voice_assistant.useOnlineTts');
    state.useOnlineTts = savedOnlineTts === '1';
    if (state.useOnlineTts) {
        onlineBtn.classList.add('active');
        onlineBtn.textContent = 'Online TTS ON';
    } else {
        onlineBtn.classList.remove('active');
        onlineBtn.textContent = 'Online TTS OFF';
    }

    addStatusLog('Voice Assistant initialized. Ready for input.', 'info');

    try {
        const response = await fetch(`${API_BASE}/api/health`);
        if (response.ok) {
            const health = await response.json();
            addStatusLog(`Backend connected: ${health.app_name} v${health.version} (${health.device})`, 'success');
        } else {
            addStatusLog('Backend connection issue. Check server.', 'warning');
        }
    } catch (error) {
        addStatusLog('Cannot reach backend. Is the server running?', 'error');
    }

    document.getElementById('devTextInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            submitDevQuery();
        }
    });

    document.getElementById('translateInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            submitTranslation();
        }
    });
});
