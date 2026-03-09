# Installation & Transcription Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all critical installation blockers and the empty-transcription bug so be-more-agent works end-to-end on a fresh Raspberry Pi 5.

**Architecture:** Seven focused patches across `setup.sh`, `requirements.txt`, `config.json`, and `agent.py`. Each patch is self-contained. Valuable audio-device robustness code from upstream PR #3 (moorew) is cherry-picked and corrected where it introduced new problems.

**Tech Stack:** Python 3.9+, Bash, whisper.cpp, Piper TTS, OpenWakeWord, Ollama, sounddevice/PortAudio, scipy

**Branch:** `fix/installation-and-transcription`
**Target remote:** `fork` → `https://github.com/lkoranda/be-more-agent`

---

## Pre-Flight: Add Fork Remote & Create Branch

```bash
git remote add fork https://github.com/lkoranda/be-more-agent.git
git fetch fork
git checkout -b fix/installation-and-transcription
```

---

## Task 1: Fix `requirements.txt` — Wrong Package Names & Missing Deps

**Problem:** `duckduckgo-search` provides `from duckduckgo_search import DDGS` but code imports `from ddgs import DDGS` (PR #3 already fixed the import side; match the package). `tflite-runtime` is required by `openwakeword` but missing. Generic `onnxruntime` has no aarch64 wheels.

**Files:**
- Modify: `requirements.txt`

**Step 1: Replace package list**

```text
sounddevice
numpy
scipy
openwakeword
onnxruntime
duckduckgo-search
Pillow
```

becomes:

```text
sounddevice
numpy
scipy
openwakeword
tflite-runtime
duckduckgo-search
Pillow
```

Note: `onnxruntime` is removed from requirements.txt — the `setup.sh` will install the correct architecture-specific build (see Task 3).

**Step 2: Verify diff**

```bash
git diff requirements.txt
```

Expected: `onnxruntime` removed, `tflite-runtime` added.

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "fix: remove onnxruntime from requirements (handled arch-specific in setup.sh), add tflite-runtime for openwakeword"
```

---

## Task 2: Fix `config.json` — Key Mismatch & Hardened Defaults

**Problem:**
- `config.json` has old `"system_prompt"` key but `agent.py` reads `"system_prompt_extras"` → KeyError on start
- PR #3 adds `"input_sample_rate": 44100` hardcoded — not all devices support 44100; auto-detect is safer
- PR #3 adds `"input_device": null` which is a valid new feature to keep
- `camera_rotation: 180` is hardware-specific — reset to 0 as default

**Files:**
- Modify: `config.json`

**Step 1: Write corrected config.json**

```json
{
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "chat_memory": true,
    "camera_rotation": 0,
    "system_prompt_extras": "",
    "input_device": null,
    "input_sample_rate": null
}
```

Key changes vs PR #3:
- `"system_prompt"` → removed (was the wrong key causing KeyError)
- `"system_prompt_extras": ""` → kept (matches code)
- `"input_sample_rate": 44100` → changed to `null` (let `choose_input_samplerate()` auto-probe)
- `"input_device": null` → kept (new useful feature)
- `"camera_rotation": 180` → reset to `0` (was user's personal hardware setting)

**Step 2: Commit**

```bash
git add config.json
git commit -m "fix: correct system_prompt_extras key, set input_sample_rate to null for auto-detect"
```

---

## Task 3: Fix `setup.sh` — Missing Deps, whisper.cpp, Ollama, faces/capturing

**Problem:** setup.sh is missing:
1. `python3-dev portaudio19-dev liblapack-dev libblas-dev` (needed for native module linking — from PR #3)
2. Architecture-specific `onnxruntime` install
3. `whisper.cpp` clone + build + model download — the #1 cause of empty transcription
4. Ollama auto-install (currently just warns if missing)
5. `faces/capturing` directory never created
6. No error handling on critical downloads

**Files:**
- Modify: `setup.sh`

**Step 1: Replace setup.sh with fixed version**

```bash
#!/bin/bash
set -e  # Exit on any error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🤖 Pi Local Assistant Setup Script${NC}"

# 1. Install System Dependencies
echo -e "${YELLOW}[1/7] Installing System Tools (apt)...${NC}"
sudo apt update
sudo apt install -y \
    python3-tk python3-dev \
    libasound2-dev portaudio19-dev \
    libatlas-base-dev liblapack-dev libblas-dev \
    cmake build-essential espeak-ng git

# 2. Create Folders (including faces/capturing)
echo -e "${YELLOW}[2/7] Creating Folders...${NC}"
mkdir -p piper
mkdir -p sounds/greeting_sounds sounds/thinking_sounds sounds/ack_sounds sounds/error_sounds
mkdir -p faces/idle faces/listening faces/thinking faces/speaking faces/error faces/warmup faces/capturing

# 3. Download Piper TTS (aarch64 only)
echo -e "${YELLOW}[3/7] Setting up Piper TTS...${NC}"
ARCH=$(uname -m)
if [ "$ARCH" == "aarch64" ]; then
    wget -O piper.tar.gz https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
    tar -xvf piper.tar.gz -C piper --strip-components=1
    rm piper.tar.gz
    if [ ! -f "piper/piper" ]; then
        echo -e "${RED}❌ Piper binary not found after extraction. Aborting.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Piper binary found at piper/piper${NC}"
else
    echo -e "${YELLOW}⚠️  Not on Raspberry Pi (aarch64). Skipping Piper download.${NC}"
fi

# 4. Download Piper Voice Model
echo -e "${YELLOW}[4/7] Downloading Voice Model...${NC}"
mkdir -p piper
wget -nc -O piper/en_GB-semaine-medium.onnx \
    https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
wget -nc -O piper/en_GB-semaine-medium.onnx.json \
    https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
if [ ! -f "piper/en_GB-semaine-medium.onnx.json" ]; then
    echo -e "${RED}❌ Voice model JSON not found. TTS will fail.${NC}"
    exit 1
fi

# 5. Install Python Libraries
echo -e "${YELLOW}[5/7] Installing Python Libraries...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip

# Force rebuild sounddevice against the newly installed PortAudio dev headers (from PR #3)
pip install --force-reinstall --no-cache-dir sounddevice

# Architecture-specific onnxruntime (avoids 30+ min compile on Pi5)
if [ "$ARCH" == "aarch64" ]; then
    echo -e "${YELLOW}Installing onnxruntime for aarch64 via piwheels...${NC}"
    pip install -i https://www.piwheels.org/simple onnxruntime
else
    pip install onnxruntime
fi

pip install -r requirements.txt

# 6. Install Ollama if missing
echo -e "${YELLOW}[6/7] Checking Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Ollama not found. Installing...${NC}"
    curl -fsSL https://ollama.ai/install.sh | sh
fi
ollama pull gemma3:1b
ollama pull moondream

# 7. Download Wake Word Model
echo -e "${YELLOW}[7/7] Setting up Wake Word...${NC}"
if [ ! -f "wakeword.onnx" ]; then
    echo -e "${YELLOW}Downloading default 'Hey Jarvis' wake word...${NC}"
    curl -L -o wakeword.onnx \
        https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/hey_jarvis_v0.1.onnx
fi
if [ ! -f "wakeword.onnx" ] || [ ! -s "wakeword.onnx" ]; then
    echo -e "${RED}❌ Failed to download wakeword.onnx. Check your internet connection.${NC}"
    exit 1
fi

# 8. Build whisper.cpp (THE key missing step — fixes empty transcription)
echo -e "${YELLOW}[8/8] Building whisper.cpp (Speech-to-Text)...${NC}"
if [ ! -d "whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git
fi
cd whisper.cpp
make -j$(nproc)
mkdir -p models
if [ ! -f "models/ggml-base.en.bin" ]; then
    echo -e "${YELLOW}Downloading Whisper base English model (~142MB)...${NC}"
    bash models/download-ggml-model.sh base.en
fi
if [ ! -f "build/bin/whisper-cli" ]; then
    echo -e "${RED}❌ whisper-cli binary not found after build. Check build output above.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ whisper-cli ready at whisper.cpp/build/bin/whisper-cli${NC}"
cd ..

echo ""
echo -e "${GREEN}✨ Setup Complete!${NC}"
echo ""
echo -e "${YELLOW}To run the agent:${NC}"
echo "  source venv/bin/activate"
echo "  python agent.py"
```

**Step 2: Verify key changes**

```bash
git diff setup.sh | grep "^+" | grep -E "whisper|capturing|portaudio|onnxruntime|ollama"
```

Expected: lines for each of the above categories.

**Step 3: Commit**

```bash
git add setup.sh
git commit -m "fix: add whisper.cpp build, onnxruntime aarch64, Ollama install, faces/capturing dir, portaudio dev headers, download validation"
```

---

## Task 4: Fix `agent.py` — DuckDuckGo Import + Audio Device Helpers (from PR #3, corrected)

**Problem:** `from ddgs import DDGS` fails. PR #3 fixes this correctly. PR #3 also adds `resolve_input_device()` and `choose_input_samplerate()` — take these as-is (they're well-designed). PR #3 also adds `DEFAULT_CONFIG` keys for `input_device` and `input_sample_rate` — take these.

**Files:**
- Modify: `agent.py` (import line ~47, DEFAULT_CONFIG ~62, add two helper functions after `load_config()`)

**Step 1: Fix import (line ~47)**

Change:
```python
from ddgs import DDGS
```
To:
```python
from duckduckgo_search import DDGS
```

**Step 2: Update DEFAULT_CONFIG (line ~62)**

Change:
```python
DEFAULT_CONFIG = {
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "chat_memory": True,
    "camera_rotation": 0,
    "system_prompt_extras": ""
}
```
To:
```python
DEFAULT_CONFIG = {
    "text_model": "gemma3:1b",
    "vision_model": "moondream",
    "voice_model": "piper/en_GB-semaine-medium.onnx",
    "chat_memory": True,
    "camera_rotation": 0,
    "system_prompt_extras": "",
    "input_device": None,
    "input_sample_rate": None
}
```

**Step 3: Add helper functions after `load_config()` block (after line ~91)**

```python
def resolve_input_device(config):
    """Resolve audio input device from config (index, name string, or None for default)."""
    requested = config.get("input_device")
    if requested in (None, "", "default"):
        return None
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[AUDIO] Device query failed: {e}", flush=True)
        return None
    if isinstance(requested, int) or (isinstance(requested, str) and requested.isdigit()):
        index = int(requested)
        if 0 <= index < len(devices):
            return index
        print(f"[AUDIO] Input device index {index} not found, using default.", flush=True)
        return None
    requested_lower = str(requested).lower()
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0 and requested_lower in dev.get("name", "").lower():
            return idx
    print(f"[AUDIO] Input device '{requested}' not found, using default.", flush=True)
    return None


def choose_input_samplerate(device, preferred=None):
    """Probe and return a supported input sample rate for the given device."""
    candidates = []
    if preferred:
        candidates.append(int(preferred))
    try:
        device_info = sd.query_devices(device)
        if "default_samplerate" in device_info:
            candidates.append(int(device_info["default_samplerate"]))
    except Exception:
        pass
    candidates.extend([48000, 44100, 32000, 16000])
    seen = set()
    for rate in candidates:
        if not rate or rate in seen:
            continue
        seen.add(rate)
        try:
            sd.check_input_settings(device=device, samplerate=rate, channels=1, dtype="int16")
            return rate
        except Exception:
            continue
    return 44100  # last-resort fallback


INPUT_DEVICE_NAME = resolve_input_device(CURRENT_CONFIG)
if INPUT_DEVICE_NAME is not None:
    try:
        _dev_info = sd.query_devices(INPUT_DEVICE_NAME)
        print(f"[AUDIO] Using input device: {_dev_info.get('name', INPUT_DEVICE_NAME)}", flush=True)
    except Exception:
        print(f"[AUDIO] Using input device index: {INPUT_DEVICE_NAME}", flush=True)
```

Note: Removed the debug `[AUDIO DEBUG]` print of all device indices that PR #3 left in production code.

**Step 4: Commit**

```bash
git add agent.py
git commit -m "feat: fix duckduckgo import, add input device resolution and adaptive sample rate helpers (from PR#3, cleaned)"
```

---

## Task 5: Fix `agent.py` — Wake Word Detection (from PR #3, corrected)

**Problem:** PR #3 rewrites `detect_wake_word_or_ptt()` with good improvements (nearest-neighbor resampling for CPU, overflow handling, retry logic) but introduces issues:
- Uses `StopIteration` for control flow (unusual, fragile)
- Raises `RuntimeError` on **first** overflow — too aggressive; single overflow is normal on Pi5
- `_listen_loop` has an indentation bug (extra space before `with sd.InputStream`)
- Debug logging unconditional (`[AUDIO DEBUG]` lines)

**Strategy:** Keep the good parts (nearest-neighbor resampling, overflow counter, retry, silence skip) but use clean control flow.

**Files:**
- Modify: `agent.py` — replace `detect_wake_word_or_ptt()` method (~line 492)

**Step 1: Replace `detect_wake_word_or_ptt()`**

```python
def detect_wake_word_or_ptt(self):
    self.set_state(BotStates.IDLE, "Waiting...")
    self.ptt_event.clear()

    if self.oww_model:
        self.oww_model.reset()

    if self.oww_model is None:
        self.ptt_event.wait()
        self.ptt_event.clear()
        return "PTT"

    CHUNK_SIZE = 1280
    OWW_SAMPLE_RATE = 16000

    input_rate = choose_input_samplerate(INPUT_DEVICE_NAME, CURRENT_CONFIG.get("input_sample_rate"))
    use_resampling = (input_rate != OWW_SAMPLE_RATE)
    input_chunk_size = int(CHUNK_SIZE * (input_rate / OWW_SAMPLE_RATE)) if use_resampling else CHUNK_SIZE

    stream_kwargs = {
        "samplerate": input_rate,
        "channels": 1,
        "dtype": "int16",
        "blocksize": input_chunk_size,
        "device": INPUT_DEVICE_NAME,
    }

    for attempt, kwargs in enumerate([stream_kwargs, {**stream_kwargs, "blocksize": 1024, "latency": "high"}]):
        try:
            result = self._wake_word_listen_loop(kwargs, CHUNK_SIZE, use_resampling or attempt > 0)
            if result:
                return result
        except Exception as e:
            if attempt == 0:
                print(f"[AUDIO] Wake word stream failed: {e}. Retrying with fallback settings...", flush=True)
            else:
                print(f"[CRITICAL] Wake word stream error: {e}. Falling back to PTT.", flush=True)
                self.ptt_event.wait()
                return "PTT"
    return "PTT"


def _wake_word_listen_loop(self, stream_kwargs, target_chunk_size, use_resampling):
    """
    Inner wake word listen loop. Returns "PTT", "CLI", or None (wake word triggered).
    Raises on stream error so caller can retry.
    """
    MAX_CONSECUTIVE_OVERFLOWS = 5
    overflow_count = 0

    with sd.InputStream(**stream_kwargs) as stream:
        while True:
            if self.ptt_event.is_set():
                self.ptt_event.clear()
                return "PTT"

            rlist, _, _ = select.select([sys.stdin], [], [], 0.001)
            if rlist:
                sys.stdin.readline()
                return "CLI"

            read_size = stream_kwargs.get("blocksize") or target_chunk_size
            data, overflow = stream.read(read_size)

            if overflow:
                overflow_count += 1
                if overflow_count >= MAX_CONSECUTIVE_OVERFLOWS:
                    raise RuntimeError(f"Audio buffer overflowed {overflow_count} consecutive times")
            else:
                overflow_count = 0

            audio_data = np.frombuffer(data, dtype=np.int16)
            if audio_data.ndim > 1:
                audio_data = audio_data.flatten()

            if use_resampling and len(audio_data) > 0:
                # Nearest-neighbor resampling: fast, avoids CPU bottleneck on Pi5
                step = len(audio_data) / target_chunk_size
                indices = np.arange(0, len(audio_data), step)[:target_chunk_size].astype(int)
                audio_data = audio_data[indices]

            # Skip prediction on silence to save CPU
            if np.max(np.abs(audio_data)) < 200:
                continue

            prediction = self.oww_model.predict(audio_data)
            for mdl in self.oww_model.prediction_buffer.keys():
                score = list(self.oww_model.prediction_buffer[mdl])[-1]
                if score > WAKE_WORD_THRESHOLD:
                    print(f"[WAKE] Triggered on '{mdl}' with score: {score:.2f}", flush=True)
                    self.oww_model.reset()
                    return None  # Wake word — caller returns "WAKE"
    return None
```

Wait — the caller needs to distinguish "PTT"/"CLI" from "WAKE". Update `detect_wake_word_or_ptt` to handle `None` return as "WAKE":

In the `detect_wake_word_or_ptt` loop:
```python
result = self._wake_word_listen_loop(kwargs, CHUNK_SIZE, use_resampling or attempt > 0)
if result is not None:
    return result  # "PTT" or "CLI"
return "WAKE"  # None = wake word triggered
```

**Step 2: Commit**

```bash
git add agent.py
git commit -m "fix: rewrite wake word loop - clean control flow, overflow counter (not first-overflow fail), remove debug logs, keep nearest-neighbor resampling and silence skip from PR#3"
```

---

## Task 6: Fix `agent.py` — Audio Recording Methods (from PR #3, corrected)

**Problem:** PR #3 adds `sd.stop()` + `time.sleep(0.2)` before recording streams — a real Pi5 fix for hardware contention. Take this as-is. Also use `choose_input_samplerate()` instead of raw `sd.query_devices()`.

**Files:**
- Modify: `agent.py` — `record_voice_adaptive()` (~line 544) and `record_voice_ptt()` (~line 585)

**Step 1: Update `record_voice_adaptive()`**

Replace the sample rate detection block at the top:
```python
# OLD:
try:
    device_info = sd.query_devices(kind='input')
    samplerate = int(device_info['default_samplerate'])
except: samplerate = 44100

# NEW:
samplerate = choose_input_samplerate(INPUT_DEVICE_NAME, CURRENT_CONFIG.get("input_sample_rate"))
```

Add stream cleanup before recording (inside the `try` block, before `with sd.InputStream`):
```python
try:
    sd.stop()
    time.sleep(0.2)
    with sd.InputStream(...):
        ...
except Exception as e:
    print(f"[AUDIO ERROR] Adaptive recording failed: {e}", flush=True)
    return None
```

**Step 2: Update `record_voice_ptt()`** — same pattern:
```python
samplerate = choose_input_samplerate(INPUT_DEVICE_NAME, CURRENT_CONFIG.get("input_sample_rate"))
# ...
try:
    sd.stop()
    time.sleep(0.2)
    with sd.InputStream(...):
        ...
except Exception as e:
    print(f"[AUDIO ERROR] PTT recording failed: {e}", flush=True)
    return None
```

**Step 3: Commit**

```bash
git add agent.py
git commit -m "fix: use choose_input_samplerate() in recording methods, add sd.stop() before stream open to fix Pi5 device contention (from PR#3)"
```

---

## Task 7: Fix `agent.py` — `save_audio_buffer()` Resample to 16kHz

**Problem:** Audio is saved at native device rate (44100/48000 Hz). whisper.cpp expects 16kHz. This causes empty or garbage transcription on ~70% of Pi setups.

**Files:**
- Modify: `agent.py` — `save_audio_buffer()` (~line 603)

**Step 1: Add 16kHz resampling before saving**

```python
def save_audio_buffer(self, buffer, filename, samplerate=16000):
    if not buffer: return None
    audio_data = np.concatenate(buffer, axis=0).flatten()
    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)

    # Resample to 16kHz for whisper.cpp compatibility
    TARGET_RATE = 16000
    if samplerate != TARGET_RATE:
        num_samples = int(len(audio_data) * (TARGET_RATE / samplerate))
        audio_data = scipy.signal.resample(audio_data, num_samples)
        samplerate = TARGET_RATE

    audio_data = (audio_data * 32767).astype(np.int16)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_data.tobytes())
    self.play_sound(self.get_random_sound(ack_sounds_dir))
    return filename
```

**Step 2: Commit**

```bash
git add agent.py
git commit -m "fix: resample audio to 16kHz in save_audio_buffer() before passing to whisper.cpp"
```

---

## Task 8: Fix `agent.py` — `transcribe_audio()` Error Handling

**Problem:** All whisper errors are caught silently. Missing binary → `FileNotFoundError` → `except Exception` → returns `""`. No returncode check, no stderr capture, no timeout.

**Files:**
- Modify: `agent.py` — `transcribe_audio()` (~line 616)

**Step 1: Replace `transcribe_audio()`**

```python
def transcribe_audio(self, filename):
    print("Transcribing...", flush=True)
    WHISPER_BIN = "./whisper.cpp/build/bin/whisper-cli"
    WHISPER_MODEL = "./whisper.cpp/models/ggml-base.en.bin"

    if not os.path.exists(WHISPER_BIN):
        print(f"[ERROR] whisper-cli not found at {WHISPER_BIN}. Run setup.sh first.", flush=True)
        return ""
    if not os.path.exists(WHISPER_MODEL):
        print(f"[ERROR] Whisper model not found at {WHISPER_MODEL}. Run setup.sh first.", flush=True)
        return ""

    try:
        result = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-l", "en", "-t", "4", "-f", filename],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            error_detail = (result.stderr or result.stdout or "no output").strip()[:200]
            print(f"[ERROR] Whisper failed (code {result.returncode}): {error_detail}", flush=True)
            return ""

        # Some whisper.cpp builds write to stderr; check both
        output = (result.stdout + result.stderr).strip()
        transcription_lines = output.split('\n')

        transcription = ""
        if transcription_lines and transcription_lines[-1].strip():
            last_line = transcription_lines[-1].strip()
            if ']' in last_line:
                transcription = last_line.split("]")[1].strip()
            else:
                transcription = last_line

        print(f"Heard: '{transcription}'", flush=True)
        return transcription.strip()

    except subprocess.TimeoutExpired:
        print("[ERROR] Whisper timed out after 60 seconds.", flush=True)
        return ""
    except Exception as e:
        print(f"[ERROR] Transcription error: {e}", flush=True)
        return ""
```

**Step 2: Commit**

```bash
git add agent.py
git commit -m "fix: transcribe_audio - pre-flight checks for missing binary/model, returncode check, stderr capture, 60s timeout"
```

---

## Task 9: Fix `agent.py` — Shutdown & Silence Threshold

**Problem:**
- PR #3 removes `sys.exit(0)` from `safe_exit()` — this can leave daemon threads hanging on exit. Keep `sys.exit(0)` but add the good parts: `exiting` flag, `sd.stop()`, try/except on `master.quit()`.
- Silence threshold `0.006` is too low (about -44 dB RMS). Raise to `0.015` for more reliable voice detection on budget USB mics.

**Files:**
- Modify: `agent.py` — `BotGUI.__init__()`, `safe_exit()` (~line 228), `record_voice_adaptive()` silence_threshold line (~line 552)

**Step 1: Add `self.exiting = False` to `__init__` (after `self.current_audio_process = None`)**

```python
self.current_audio_process = None
self.exiting = False
```

**Step 2: Replace `safe_exit()`**

```python
def safe_exit(self):
    if self.exiting:
        return
    self.exiting = True
    print("\n--- SHUTDOWN SEQUENCE ---", flush=True)
    if self.current_audio_process:
        try:
            self.current_audio_process.terminate()
            self.current_audio_process.wait(timeout=1)
        except: pass

    self.recording_active.clear()
    self.thinking_sound_active.clear()
    self.tts_active.clear()

    self.save_chat_history()

    try:
        ollama.generate(model=TEXT_MODEL, prompt="", keep_alive=0)
    except: pass

    try:
        sd.stop()
    except: pass

    try:
        self.master.quit()
    except Exception: pass

    sys.exit(0)
```

**Step 3: Update silence threshold in `record_voice_adaptive()`**

```python
# OLD:
silence_threshold = 0.006
# NEW:
silence_threshold = 0.015
```

**Step 4: Commit**

```bash
git add agent.py
git commit -m "fix: harden safe_exit with exiting flag + sd.stop() (from PR#3), keep sys.exit(0) for clean thread termination, raise silence threshold 0.006->0.015"
```

---

## Task 10: Fix Launcher Scripts — Remove Hardcoded Paths

**Problem:** PR #3's `start_agent.sh` and `be-more-agent.desktop` have hardcoded `/home/clevercode/be-more-agent/` paths. These break on any other system.

**Files:**
- Modify: `start_agent.sh`
- Modify: `be-more-agent.desktop`

**Step 1: Fix `start_agent.sh`**

```bash
#!/bin/bash
set -euo pipefail

# Resolve the directory containing this script regardless of where it's called from
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$BASE_DIR"

if [ ! -f "$BASE_DIR/venv/bin/activate" ]; then
    echo "Virtual environment not found. Run setup.sh first."
    exit 1
fi

source "$BASE_DIR/venv/bin/activate"
exec python "$BASE_DIR/agent.py"
```

**Step 2: Fix `be-more-agent.desktop`**

```ini
[Desktop Entry]
Type=Application
Name=Be More Agent
Comment=Launch the Be More Agent
Exec=bash -c 'cd %k && ./start_agent.sh'
Path=/opt/be-more-agent
Icon=utilities-terminal
Terminal=true
Categories=Utility;
```

Note: `Path` and `Icon` still need to be customized per install — add a comment in the file noting this. The `Exec` line is now self-referential rather than hardcoded.

Better approach: ship a `install-desktop.sh` script that generates the `.desktop` with the correct path:

```bash
#!/bin/bash
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/be-more-agent.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Be More Agent
Comment=Launch the Be More Agent
Exec=$INSTALL_DIR/start_agent.sh
Path=$INSTALL_DIR
Icon=$INSTALL_DIR/faces/idle/idle_0.png
Terminal=true
Categories=Utility;
EOF
echo "Desktop entry installed to $DESKTOP_FILE"
```

**Step 3: Commit**

```bash
git add start_agent.sh be-more-agent.desktop
git commit -m "fix: remove hardcoded /home/clevercode paths - start_agent.sh now self-resolves, add install-desktop.sh for portable desktop entry"
```

---

## Task 11: Update README

**Problem:** README says `ollama pull gemma:2b` but code uses `gemma3:1b`. Add whisper.cpp build note to installation section.

**Files:**
- Modify: `README.md`

**Step 1: Fix model reference**

In the Prerequisites section, change:
```markdown
ollama pull gemma:2b
ollama pull moondream
```
To:
```markdown
ollama pull gemma3:1b
ollama pull moondream
```
Note: `setup.sh` handles this automatically now, but the manual instructions should match.

**Step 2: Add whisper.cpp note to the Installation section**

Add under "Clone & Setup":
```markdown
*The setup script will install system libraries, create necessary folders, download Piper TTS, build whisper.cpp (speech-to-text), and set up the Python virtual environment. **Note:** The whisper.cpp build step can take 5–10 minutes on a Raspberry Pi 5.*
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix model name gemma:2b -> gemma3:1b, note whisper.cpp build time in setup instructions"
```

---

## Task 12: Push & Create PR

**Step 1: Push branch to fork**

```bash
git push -u fork fix/installation-and-transcription
```

**Step 2: Create PR against upstream**

```bash
gh pr create \
  --repo brenpoly/be-more-agent \
  --head lkoranda:fix/installation-and-transcription \
  --base main \
  --title "fix: complete installation and empty-transcription fix for Raspberry Pi 5" \
  --body "$(cat <<'EOF'
## Summary

- **Fixes empty transcription (100% fresh-install failure):** Adds `whisper.cpp` clone + build + model download to `setup.sh` — the binary never existed before
- **Fixes audio format mismatch:** Resample audio to 16kHz in `save_audio_buffer()` before passing to whisper.cpp (was saving at 44100/48000 Hz)
- **Fixes silent failures in `transcribe_audio()`:** Pre-flight checks for missing binary/model, returncode check, stderr capture, 60s timeout
- **Fixes broken imports and missing deps:** `ddgs` → `duckduckgo_search`, adds `tflite-runtime`, arch-specific `onnxruntime` via piwheels
- **Fixes config key mismatch:** `system_prompt` → `system_prompt_extras` (was causing KeyError on start)
- **Fixes `faces/capturing` directory missing** (crash on image capture state)
- **Adds Ollama auto-install** to `setup.sh`
- **Cherry-picks audio robustness from PR #3 (moorew):** input device resolution, adaptive sample rate probing, `sd.stop()` before recording, nearest-neighbor resampling in wake word loop (CPU fix), overflow counter, shutdown hardening
- **Fixes issues introduced by PR #3:** removes hardcoded `/home/clevercode/` paths, removes unconditional debug logging, fixes `StopIteration` control flow, changes first-overflow-fail to consecutive-overflow counter
- **Raises silence threshold** `0.006` → `0.015` for better voice detection on budget USB mics

## Test plan

- [ ] Fresh `./setup.sh` completes without error on Raspberry Pi 5
- [ ] `whisper.cpp/build/bin/whisper-cli` exists after setup
- [ ] `python agent.py` starts without import or KeyError
- [ ] Wake word triggers `LISTENING` state
- [ ] Speaking returns non-empty transcription (no more "Transcription empty.")
- [ ] PTT mode (Enter key) records and transcribes
- [ ] Image capture state (`faces/capturing`) does not crash
- [ ] `start_agent.sh` works from any directory (not just `/home/clevercode/`)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Summary of All Changes

| Task | File(s) | What it fixes |
|------|---------|---------------|
| 1 | `requirements.txt` | Remove `onnxruntime`, add `tflite-runtime` |
| 2 | `config.json` | Fix `system_prompt_extras` key, `input_sample_rate: null` |
| 3 | `setup.sh` | whisper.cpp build, Ollama install, aarch64 onnxruntime, dev headers, `faces/capturing`, download validation |
| 4 | `agent.py` | Fix DuckDuckGo import, add device resolution helpers from PR#3 (cleaned) |
| 5 | `agent.py` | Wake word loop rewrite from PR#3 — clean control flow, overflow counter |
| 6 | `agent.py` | Recording methods — `choose_input_samplerate()`, `sd.stop()` before stream |
| 7 | `agent.py` | `save_audio_buffer()` — resample to 16kHz for whisper |
| 8 | `agent.py` | `transcribe_audio()` — pre-flight checks, returncode, stderr, timeout |
| 9 | `agent.py` | Shutdown hardening, silence threshold 0.006→0.015 |
| 10 | `start_agent.sh`, `be-more-agent.desktop` | Remove hardcoded paths |
| 11 | `README.md` | Fix model name, note whisper build time |
| 12 | — | Push + create PR |
