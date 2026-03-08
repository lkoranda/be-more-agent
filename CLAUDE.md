# be-more-agent — Claude Code Project Context

## What This Is

A local, offline-first AI voice agent for Raspberry Pi 5. Listens for a wake word, records speech, transcribes via whisper.cpp, queries Ollama (local LLM), and speaks back with Piper TTS. Displays animated face on a connected LCD screen.

## Key Architecture

```
Wake Word (OpenWakeWord) → Record Audio → Whisper.cpp STT → Ollama LLM → Piper TTS → Speaker
                                                                    ↓
                                                         Action Router (get_time, search_web, capture_image)
```

Single-file agent: `agent.py`. All logic is in `BotGUI` class with a background thread (`safe_main_execution`).

## Critical File Map

| File | Purpose |
|------|---------|
| `agent.py` | Everything — GUI, audio pipeline, wake word, STT, LLM, TTS |
| `setup.sh` | Full installer — must be run on Pi before `agent.py` |
| `config.json` | Runtime config — text_model, voice_model, input_device, etc. |
| `requirements.txt` | Python deps (no `onnxruntime` — handled arch-specifically in setup.sh) |
| `wakeword.onnx` | OpenWakeWord model file |
| `whisper.cpp/` | Speech-to-text engine (cloned + built by setup.sh) |
| `piper/` | TTS engine binary + voice models |
| `faces/<state>/` | PNG sequences for each bot state (idle/listening/thinking/speaking/error/warmup/capturing) |
| `sounds/<category>/` | WAV sound effects played at various events |

## Key Config Keys (config.json)

- `text_model` — Ollama model name (default: `gemma3:1b`)
- `vision_model` — Vision model (default: `moondream`)
- `voice_model` — Piper voice model path (default: `piper/en_GB-semaine-medium.onnx`)
- `system_prompt_extras` — Extra instructions appended to base system prompt (NOT `system_prompt`)
- `input_device` — Audio input device index or partial name string, null = system default
- `input_sample_rate` — Preferred input sample rate, null = auto-detect via `choose_input_samplerate()`
- `camera_rotation` — Degrees to rotate camera image (0, 90, 180, 270)

## Known Gotchas

### Transcription empty
The most common failure. Root causes:
1. `whisper.cpp/build/bin/whisper-cli` doesn't exist — run `setup.sh`
2. `whisper.cpp/models/ggml-base.en.bin` doesn't exist — run `setup.sh`
3. Audio was saved at wrong sample rate (44100/48000 Hz) — `save_audio_buffer()` must resample to 16kHz

### Import error on start
`from duckduckgo_search import DDGS` — PyPI package is `duckduckgo-search`, import is `duckduckgo_search`

### openwakeword fails to import
Needs `tflite-runtime` (in requirements.txt). On Pi5 also needs `onnxruntime` installed via piwheels (arch-specific).

### Audio device contention on Pi5
Always call `sd.stop()` + `time.sleep(0.2)` before opening a new `sd.InputStream`. Skipping this causes ALSA "Device or resource busy" errors.

### Piper binary location
Binary at `./piper/piper`, voice model at `piper/en_GB-semaine-medium.onnx` (+ `.onnx.json` required).

## Audio Pipeline Details

- **Wake word**: runs at 16kHz int16. Uses nearest-neighbor resampling (not scipy) to avoid CPU overflow on Pi5.
- **Recording**: captured at device native rate via `choose_input_samplerate()`, then resampled to 16kHz before saving to WAV.
- **whisper.cpp**: called via subprocess. Check `result.returncode` before parsing stdout. Some builds output to stderr — check both.
- **Piper TTS**: called via subprocess stdin/stdout pipe. Output is raw int16 PCM at 22050 Hz.

## Bot States

`BotStates`: IDLE → LISTENING → THINKING → SPEAKING → back to IDLE
Also: WARMUP (startup), CAPTURING (camera), ERROR

Each state has a corresponding `faces/<state>/` PNG animation directory.

## Development Notes

- No test suite — hardware project. Verify changes by running on Pi or checking logic manually.
- `INPUT_DEVICE_NAME` is a module-level variable resolved at import time via `resolve_input_device()`.
- The `OLLAMA_OPTIONS` dict controls model behavior (num_thread=4 is Pi5-appropriate).
- Memory is capped at 10 conversation turns in `save_chat_history()`.
- `sys.exit(0)` in `safe_exit()` is intentional — needed to kill daemon threads cleanly.

## Setup Checklist (fresh Pi5)

```bash
# 1. Install Ollama first (setup.sh does this if missing)
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Run setup
git clone https://github.com/lkoranda/be-more-agent.git
cd be-more-agent
chmod +x setup.sh
./setup.sh  # Takes 10-15 min on Pi5 (whisper.cpp build)

# 3. Run
source venv/bin/activate
python agent.py
```
