#!/bin/bash
set -e  # Exit on any error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🤖 Pi Local Assistant Setup Script${NC}"

# 1. Install System Dependencies
echo -e "${YELLOW}[1/9] Installing System Tools (apt)...${NC}"
sudo apt update
sudo apt install -y \
    python3-tk python3-dev \
    libasound2-dev portaudio19-dev \
    libopenblas-dev liblapack-dev libblas-dev \
    cmake build-essential espeak-ng git

# 2. Create Folders (including faces/capturing)
echo -e "${YELLOW}[2/9] Creating Folders...${NC}"
mkdir -p piper
mkdir -p sounds/greeting_sounds sounds/thinking_sounds sounds/ack_sounds sounds/error_sounds
mkdir -p faces/idle faces/listening faces/thinking faces/speaking faces/error faces/warmup faces/capturing

# 3. Download Piper TTS (aarch64 only)
echo -e "${YELLOW}[3/9] Setting up Piper TTS...${NC}"
ARCH=$(uname -m)
if [ "$ARCH" == "aarch64" ]; then
    if [ -f "piper/piper" ]; then
        echo -e "${GREEN}✓ Piper binary already installed, skipping download.${NC}"
    else
        wget -O piper.tar.gz https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
        tar -xvf piper.tar.gz -C piper --strip-components=1
        rm piper.tar.gz
        if [ ! -f "piper/piper" ]; then
            echo -e "${RED}❌ Piper binary not found after extraction. Aborting.${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Piper binary installed at piper/piper${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Not on Raspberry Pi (aarch64). Skipping Piper download.${NC}"
fi

# 4. Download Piper Voice Model
# Use -s (non-empty size check) rather than -f so partially-downloaded files are re-fetched
echo -e "${YELLOW}[4/9] Downloading Voice Model...${NC}"
mkdir -p piper
for MODEL_FILE in "en_GB-semaine-medium.onnx" "en_GB-semaine-medium.onnx.json"; do
    DEST="piper/$MODEL_FILE"
    if [ -s "$DEST" ]; then
        echo -e "${GREEN}✓ $MODEL_FILE already present, skipping.${NC}"
    else
        echo -e "${YELLOW}  Downloading $MODEL_FILE...${NC}"
        wget -O "$DEST" \
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/$MODEL_FILE"
    fi
done
if [ ! -s "piper/en_GB-semaine-medium.onnx" ] || [ ! -s "piper/en_GB-semaine-medium.onnx.json" ]; then
    echo -e "${RED}❌ Voice model files missing or empty after download. TTS will fail.${NC}"
    exit 1
fi

# 5. Install Python Libraries
echo -e "${YELLOW}[5/9] Installing Python Libraries...${NC}"
if [ -d "venv" ]; then
    VENV_PY=$(venv/bin/python --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    SYS_PY=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$VENV_PY" != "$SYS_PY" ]; then
        echo -e "${YELLOW}Python version mismatch (venv: $VENV_PY, system: $SYS_PY). Recreating venv...${NC}"
        rm -rf venv
    fi
fi
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip

# Force rebuild sounddevice against the newly installed PortAudio dev headers
pip install --force-reinstall --no-cache-dir sounddevice

# onnxruntime — PyPI has aarch64 wheels since v1.16, installs directly on Pi5
pip install onnxruntime

pip install -r requirements.txt

# 6. Install Ollama if missing
echo -e "${YELLOW}[6/9] Checking Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Ollama not found. Installing...${NC}"
    curl -fsSL https://ollama.ai/install.sh | sh
fi
ollama pull gemma3:1b
ollama pull moondream

# 7. Download Wake Word Model
echo -e "${YELLOW}[7/9] Setting up Wake Word...${NC}"
if [ ! -f "wakeword.onnx" ]; then
    echo -e "${YELLOW}Downloading default 'Hey Jarvis' wake word...${NC}"
    curl -L -o wakeword.onnx \
        https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/hey_jarvis_v0.1.onnx
fi
if [ ! -f "wakeword.onnx" ] || [ ! -s "wakeword.onnx" ]; then
    echo -e "${RED}❌ Failed to download wakeword.onnx. Check your internet connection.${NC}"
    exit 1
fi

# 8. Build whisper.cpp (THE key missing step — fixes empty transcription on all fresh installs)
echo -e "${YELLOW}[8/9] Building whisper.cpp (Speech-to-Text engine)...${NC}"
if [ ! -d "whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git
fi
cd whisper.cpp

if [ -f "build/bin/whisper-cli" ]; then
    echo -e "${GREEN}✓ whisper-cli already built, skipping cmake build.${NC}"
else
    echo -e "${YELLOW}      Building whisper-cli — takes 3-5 minutes on Raspberry Pi 5...${NC}"
    cmake -B build -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
    cmake --build build --config Release -j$(nproc)
    if [ ! -f "build/bin/whisper-cli" ]; then
        echo -e "${RED}❌ whisper-cli binary not found after build. Check build output above.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ whisper-cli built at whisper.cpp/build/bin/whisper-cli${NC}"
fi

mkdir -p models
if [ -s "models/ggml-base.en.bin" ]; then
    echo -e "${GREEN}✓ Whisper model already present, skipping download.${NC}"
else
    echo -e "${YELLOW}Downloading Whisper base English model (~142MB)...${NC}"
    bash models/download-ggml-model.sh base.en
fi
cd ..

# 9. USB mic ALSA gain + full stack verification
echo -e "${YELLOW}[9/9] Verifying stack and checking audio levels...${NC}"

# Boost USB mic capture gain — Pi5 USB mics often default to near-zero
if command -v amixer &>/dev/null; then
    USB_CARD=$(arecord -l 2>/dev/null | grep -i "usb" | grep -oP 'card \K[0-9]+' | head -1)
    if [ -n "$USB_CARD" ]; then
        echo -e "${YELLOW}  USB audio on ALSA card $USB_CARD — normalizing capture volume to 80%...${NC}"
        for ctrl in "Mic" "Capture" "Mic Capture Volume" "PCM Capture Volume" \
                    "Mic Boost" "Digital Capture Volume"; do
            amixer -c "$USB_CARD" sset "$ctrl" 80% 2>/dev/null \
                && echo -e "${GREEN}    ✓ Set '$ctrl' to 80%${NC}"
        done
        # Disable Auto Gain Control — causes unpredictable mic levels
        amixer -c "$USB_CARD" sset "Auto Gain Control" off 2>/dev/null \
            && echo -e "${GREEN}    ✓ Disabled Auto Gain Control${NC}"
    else
        echo -e "${YELLOW}  No USB audio card detected via arecord — skipping ALSA gain step${NC}"
    fi
else
    echo -e "${YELLOW}  amixer not found — skipping ALSA gain step (install alsa-utils)${NC}"
fi

# Run full stack verification (non-blocking — verify.sh exits 0 even with warnings)
if [ -f "verify.sh" ]; then
    echo ""
    bash verify.sh || true
else
    echo -e "${YELLOW}  verify.sh not found — skipping stack verification${NC}"
fi

echo ""
echo -e "${GREEN}✨ Setup Complete!${NC}"
echo ""
echo -e "${YELLOW}To run the agent:${NC}"
echo "  source venv/bin/activate"
echo "  python agent.py"
echo ""
echo -e "${YELLOW}To re-run verification at any time:${NC}"
echo "  source venv/bin/activate && bash verify.sh"
