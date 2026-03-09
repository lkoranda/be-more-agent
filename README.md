# Be More Agent 🤖
**A Customizable, Offline-First AI Agent for Raspberry Pi**

[![Watch the Demo](https://img.youtube.com/vi/l5ggH-YhuAw/maxresdefault.jpg)](https://youtu.be/l5ggH-YhuAw)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red) ![License](https://img.shields.io/badge/License-MIT-green)

This project turns a Raspberry Pi into a fully functional, conversational AI agent. Unlike cloud-based assistants, this agent runs **100% locally** on your device. It listens for a wake word, processes speech, "thinks" using a local Large Language Model (LLM), and speaks back with a low-latency neural voice—all while displaying reactive face animations.

**It is designed as a blank canvas:** You can easily swap the face images and sound effects to create your own character!

## ✨ Features

* **100% Local Intelligence**: Powered by **Ollama** (LLM) and **Whisper.cpp** (Speech-to-Text). No API fees, no cloud data usage.
* **Open Source Wake Word**: Wakes up to your custom model using **OpenWakeWord** (Offline & Free). No access keys required.
* **Hardware-Aware Audio**: Automatically detects your microphone's sample rate and resamples audio on the fly to prevent ALSA errors.
* **Smart Web Search**: Uses DuckDuckGo to find real-time news and information when the LLM doesn't know the answer.
* **Reactive Faces**: The GUI updates the character's face based on its state (Listening, Thinking, Speaking, Idle).
* **Fast Text-to-Speech**: Uses **Piper TTS** for low-latency, high-quality voice generation on the Pi.
* **Vision Capable**: Can "see" and describe the world using a connected camera and the **Moondream** vision model.

## 🛠️ Hardware Requirements

* **Raspberry Pi 5** (Recommended) or Pi 4 (4GB RAM minimum)
* USB Microphone & Speaker
* LCD Screen (DSI or HDMI)
* Raspberry Pi Camera Module

---

## 📂 Project Structure

```text
be-more-agent/
├── agent.py                   # The main brain script
├── setup.sh                   # Auto-installer script
├── wakeword.onnx              # OpenWakeWord model (The "Ear")
├── config.json                # User settings (Models, Prompt, Hardware)
├── chat_memory.json           # Conversation history
├── requirements.txt           # Python dependencies
├── whisper.cpp/               # Speech-to-Text engine
├── piper/                     # Piper TTS engine & voice models
├── sounds/                    # Sound effects folder
│   ├── greeting_sounds/       # Startup .wav files
│   ├── thinking_sounds/       # Looping .wav files
│   ├── ack_sounds/            # "I heard you" .wav files
│   └── error_sounds/          # Error/Confusion .wav files
└── faces/                     # Face images folder
    ├── idle/                  # .png sequence for idle state
    ├── listening/             # .png sequence for listening
    ├── thinking/              # .png sequence for thinking
    ├── speaking/              # .png sequence for speaking
    ├── error/                 # .png sequence for errors
    └── warmup/                # .png sequence for startup
```

---

## 🚀 Installation

### 1. Prerequisites
Ensure your Raspberry Pi OS is up to date.
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git -y
```

### 2. Install Ollama
This agent relies on [Ollama](https://ollama.com) to run the brain.
```bash
curl -fsSL https://ollama.com/install.sh| sh
```
*Pull the required models:*
```bash
ollama pull gemma3:1b
ollama pull moondream
```

### 3. Clone & Setup
```bash
git clone https://github.com/brenpoly/be-more-agent.git
cd be-more-agent
chmod +x setup.sh
./setup.sh
```
*The setup script will install system libraries, create necessary folders, download Piper TTS, build whisper.cpp (speech-to-text engine), and set up the Python virtual environment. **Note:** The whisper.cpp build step can take 5–10 minutes on a Raspberry Pi 5.*

### 4. Configure the Wake Word
The setup script downloads a default wake word ("Hey Jarvis"). To use your own:
1. Train a model at [OpenWakeWord](https://github.com/dscripka/openWakeWord).
2. Place the `.onnx` file in the root folder.
3. Rename it to `wakeword.onnx`.

### 5. Run the Agent
```bash
source venv/bin/activate
python agent.py
```

---

## 📂 Configuration (`config.json`)

All keys are optional — missing keys fall back to built-in defaults. Edit `config.json` in the project root to customise behaviour without touching code.

```json
{
    "text_model":           "gemma3:1b",
    "vision_model":         "moondream",
    "voice_model":          "piper/en_GB-semaine-medium.onnx",

    "system_prompt_extras": "",
    "chat_memory":          true,

    "wake_word_model":      "./wakeword.onnx",
    "wake_word_threshold":  0.5,

    "silence_to_stop":      1.5,

    "whisper_language":     "en",
    "whisper_threads":      4,

    "llm_temperature":      0.7,
    "llm_threads":          4,

    "camera_rotation":      0,
    "input_device":         null,
    "input_sample_rate":    null,
    "output_device":        null
}
```

### Key reference

| Key | Default | Description |
|-----|---------|-------------|
| `text_model` | `gemma3:1b` | Ollama model used for conversation. Swap for a larger model if your Pi has enough RAM (e.g. `gemma3:4b`). |
| `vision_model` | `moondream` | Ollama model used when the agent looks at the camera. |
| `voice_model` | `piper/en_GB-semaine-medium.onnx` | Path to the Piper `.onnx` voice file. |
| `system_prompt_extras` | `""` | Extra instructions appended to the system prompt. Use this to define personality, e.g. `"You are a pirate. Always speak like one."` |
| `chat_memory` | `true` | Keep conversation history across turns. Set to `false` for stateless one-shot queries. |
| `wake_word_model` | `./wakeword.onnx` | Path to the OpenWakeWord `.onnx` model file. Replace with your own trained wake word. |
| `wake_word_threshold` | `0.5` | Detection confidence cutoff (0.0–1.0). Lower (e.g. `0.3`) = more sensitive, triggers more easily. Higher (e.g. `0.7`) = stricter, fewer false positives. |
| `silence_to_stop` | `1.5` | Seconds of silence after speaking before recording stops. Raise to `2.0–2.5` if it cuts you off mid-sentence; lower to `0.8–1.0` for snappier responses. |
| `whisper_model` | `"base.en"` | Whisper model size. `"tiny.en"` is ~2× faster with slightly lower accuracy (good for quiet, clear speech). `"base.en"` is the default. Must be downloaded first: `cd whisper.cpp && bash models/download-ggml-model.sh tiny.en` |
| `whisper_language` | `"en"` | Language code for transcription. Use `"auto"` to detect automatically, or a code like `"de"`, `"fr"`, `"sk"`, etc. |
| `whisper_threads` | `4` | CPU threads for the Whisper transcription process. |
| `llm_temperature` | `0.7` | LLM response creativity (0.0–1.0). `0.3` = factual and concise; `0.9` = creative and varied. |
| `llm_threads` | `4` | CPU threads allocated to Ollama. Pi 5 has 4 cores; reduce to `3` on Pi 4 to leave headroom. |
| `thinking_mode` | `false` | **Qwen3/3.5 only.** When `false`, appends `/no_think` to each message, disabling the internal reasoning block for faster responses. Set to `true` to enable step-by-step reasoning (better accuracy on complex questions, higher latency). Has no effect on other models. |
| `camera_rotation` | `0` | Rotate the camera image before sending to the vision model. Accepted values: `0`, `90`, `180`, `270`. |
| `input_device` | `null` | Audio input override. `null` = auto-select first USB microphone. Set to a device name (partial match) or index number to force a specific device. |
| `input_sample_rate` | `null` | Preferred sample rate for the input device. `null` = auto-detect. |
| `output_device` | `null` | Audio output override. `null` = auto-select first USB speaker. Set to a device name or index to force a specific device. |

---

## 🎨 Customizing Your Character

This software is a generic framework. You can give it a new personality by replacing the assets:

1.  **Faces:** The script looks for PNG sequences in `faces/[state]/`. It will loop through all images found in the folder.
2.  **Sounds:** Put multiple `.wav` files in the `sounds/[category]/` folders. The robot will pick one at random each time (e.g., different "thinking" hums or "error" buzzes).

---

## 🧠 Recommended Models (Raspberry Pi 5)

The default models (`gemma3:1b` + `moondream`) are conservative starting points. With **Pi 5 16 GB RAM** you can run significantly more capable models. All run fully offline via Ollama.

The practical speed floor for a comfortable voice assistant is ~5 tok/s — below that, pauses between TTS sentences become noticeable.

### Full comparison (Pi 5 16 GB, CPU inference)

| Model | Ollama tag | Q4 RAM | GPQA | Vision | Est. tok/s | Notes |
|-------|-----------|--------|------|--------|-----------|-------|
| **Qwen3-30B-A3B** | see below | ~12 GB | 30B-class | ❌ | ~8 | ⭐ Best quality that fits — MoE, text only |
| **Qwen3.5 9B** | `qwen3.5:9b` | ~5 GB | 81.7 | ✅ native | 2–4 | Best reasoning with vision |
| **Qwen3.5 4B** | `qwen3.5:4b` | ~2.5 GB | ~74 | ✅ native | 5–8 | Best all-round with vision |
| **Qwen3.5 2B** | `qwen3.5:2b` | ~1.5 GB | ~55 | ✅ native | 12–18 | Best speed+vision combo |
| **Qwen3.5 0.8B** | `qwen3.5:0.8b` | ~0.6 GB | ~35 | ✅ native | 20–30 | Ultra-fast, limited reasoning |
| **Gemma 3n E4B** | `gemma3n:e4b` | ~3 GB | n/a | ✅ vision+audio | 8–15 | Edge-optimised ARM, audio input |
| **Gemma 3n E2B** | `gemma3n:e2b` | ~2 GB | n/a | ✅ vision+audio | 12–20 | Fastest multimodal option |
| **Gemma 3 4B QAT** | `gemma3:4b-it-qat` | ~3 GB | ~42 | ✅ | 4–6 | QAT = near full-precision quality at int4 |
| **Gemma 3 1B** | `gemma3:1b` | ~0.8 GB | low | ❌ | ~10 | Default — simple tasks only |
| **Phi-4-mini** | `phi4-mini` | ~2.3 GB | 30–49 | ❌ | 6–10 | Outstanding STEM/math/coding |
| **Phi-4-mini reasoning** | `phi4-mini-reasoning` | ~2.3 GB | 49 | ❌ | 6–10 | Best for structured reasoning chains |
| **Ministral 3B** | `ministral:3b` | ~2 GB | n/a | ❌ | 8–12 | Strong function/tool calling |
| **SmolLM2 1.7B** | `smollm2:1.7b` | ~1 GB | n/a | ❌ | 15–20 | Ultra-lightweight, text only |
| **Llama 3.2 3B** | `llama3.2:3b` | ~2 GB | n/a | ❌ | 6–10 | Decent, outclassed by Qwen3.5:2b |
| **Qwen3.5 35B-A3B** | `qwen3.5:35b-a3b` | ~22 GB | — | ✅ | n/a | ❌ Does NOT fit in 16 GB |
| **Llama 4 Scout** | `llama4:scout` | ~55 GB | — | ✅ | n/a | ❌ Requires H100, not for Pi |
| **Mistral Small 3.2** | `mistral-small3.2` | ~14 GB | — | ✅ | <1 | ❌ Too slow on CPU |

### Recommendations by use case

**Best all-round (16 GB Pi 5)**
```json
{ "text_model": "qwen3.5:4b", "vision_model": "qwen3.5:4b" }
```
Qwen3.5 4B has native vision baked in — one model covers both text and camera. GPQA ~74 is well ahead of any competitor at this size.

**Fastest conversational (responses under 1 second)**
```json
{ "text_model": "qwen3.5:2b", "vision_model": "qwen3.5:2b" }
```
12–18 tok/s makes pauses essentially imperceptible. Retains native vision and 256K context.

**Best quality (patient user)**
```json
{ "text_model": "qwen3.5:9b", "vision_model": "qwen3.5:9b" }
```
GPQA 81.7 — beats GPT-OSS-120B on graduate-level science questions. Fits in 16 GB with ~10 GB to spare.

**Best for STEM / coding assistant**
```json
{ "text_model": "phi4-mini-reasoning", "vision_model": "moondream" }
```
Phi-4-mini reasoning matches DeepSeek-R1-Distill 7B on AIME math at 3.8B parameters.

**Best quality, text-only (16 GB Pi 5)**

Qwen3-30B-A3B is a Mixture-of-Experts model — 30B total parameters but only ~3.3B active per token. This gives it 30B-class knowledge at ~8 tok/s inference speed, comparable to Qwen3.5:4b but far more capable. No vision support; pair with a small vision model for the camera.

> **Important:** The default `ollama pull qwen3:30b-a3b` pulls a 19 GB Q4_K_M quant that **does not fit** in 16 GB. Use the byteshape KQ-2 quant instead:

```bash
# KQ-2: ~8 tok/s, 94% of BF16 quality, ~12 GB RAM (recommended)
ollama run hf.co/byteshape/Qwen3-30B-A3B-Instruct-2507-GGUF:KQ-2.gguf

# KQ-5: ~6.7 tok/s, 98% of BF16 quality, ~14.5 GB RAM (higher quality, tighter fit)
ollama run hf.co/byteshape/Qwen3-30B-A3B-Instruct-2507-GGUF:KQ-5.gguf
```

Once pulled, set in `config.json`:
```json
{
    "text_model":   "hf.co/byteshape/Qwen3-30B-A3B-Instruct-2507-GGUF:KQ-2.gguf",
    "vision_model": "qwen3.5:2b"
}
```

**Interesting alternative — Gemma 3n E4B**
```json
{ "text_model": "gemma3n:e4b", "vision_model": "gemma3n:e4b" }
```
Purpose-built for ARM edge devices. LMArena >1300 (first sub-10B to hit this). Has **audio input natively** — potentially useful for a voice pipeline. Worth benchmarking against Qwen3.5:4b on your specific Pi.

### Qwen3.5 as a single model for text + vision

All Qwen3.5 models have vision baked in (early fusion multimodal training, not a bolt-on). Use one model for everything:

```json
{
    "text_model":   "qwen3.5:4b",
    "vision_model": "qwen3.5:4b"
}
```

> **Note:** Qwen3.5 vision in Ollama requires an updated GGUF build (released March 5, 2026). Run `ollama pull qwen3.5:4b` to get the latest. If the camera command produces errors, update Ollama first.

### Pull models

```bash
# Recommended starting point (vision + text, ~3 GB)
ollama pull qwen3.5:4b

# Best quality with vision (~5 GB)
ollama pull qwen3.5:9b

# Maximum speed with vision (~1.5 GB)
ollama pull qwen3.5:2b

# Best quality text-only — MoE, ~12 GB, ~8 tok/s on Pi5
ollama run hf.co/byteshape/Qwen3-30B-A3B-Instruct-2507-GGUF:KQ-2.gguf
```

---

## ⚠️ Troubleshooting

* **"No search library found":** If web search fails, ensure you are in the virtual environment and `duckduckgo-search` is installed via pip.
* **Shutdown Errors:** When you exit the script (Ctrl+C), you might see `Expression 'alsa_snd_pcm_mmap_begin' failed`. **This is normal.** It just means the audio stream was cut off mid-sample. It does not affect the functionality.
* **Audio Glitches:** If the voice sounds fast or slow, the script attempts to auto-detect sample rates. Ensure your `config.json` points to a valid `.onnx` voice model in the `piper/` folder.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

## ⚖️ Legal Disclaimer
**"BMO"** and **"Adventure Time"** are trademarks of **Cartoon Network** (Warner Bros. Discovery).

This project is a **fan creation** built for educational and hobbyist purposes only. It is **not** affiliated with, endorsed by, or connected to Cartoon Network or the official Adventure Time brand in any way. The software provided here is a generic agent framework; users are responsible for the assets they load into it.
