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
| `whisper_language` | `"en"` | Language code for transcription. Use `"auto"` to detect automatically, or a code like `"de"`, `"fr"`, `"sk"`, etc. |
| `whisper_threads` | `4` | CPU threads for the Whisper transcription process. |
| `llm_temperature` | `0.7` | LLM response creativity (0.0–1.0). `0.3` = factual and concise; `0.9` = creative and varied. |
| `llm_threads` | `4` | CPU threads allocated to Ollama. Pi 5 has 4 cores; reduce to `3` on Pi 4 to leave headroom. |
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

## ⚠️ Troubleshooting

* **"No search library found":** If web search fails, ensure you are in the virtual environment and `duckduckgo-search` is installed via pip.
* **Shutdown Errors:** When you exit the script (Ctrl+C), you might see `Expression 'alsa_snd_pcm_mmap_begin' failed`. **This is normal.** It just means the audio stream was cut off mid-sample. It does not affect the functionality.
* **Audio Glitches:** If the voice sounds fast or slow, the script attempts to auto-detect sample rates. Ensure your `config.json` points to a valid `.onnx` voice model in the `piper/` folder.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

## ⚖️ Legal Disclaimer
**"BMO"** and **"Adventure Time"** are trademarks of **Cartoon Network** (Warner Bros. Discovery).

This project is a **fan creation** built for educational and hobbyist purposes only. It is **not** affiliated with, endorsed by, or connected to Cartoon Network or the official Adventure Time brand in any way. The software provided here is a generic agent framework; users are responsible for the assets they load into it.
