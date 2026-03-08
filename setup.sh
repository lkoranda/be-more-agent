#!/bin/bash
set -e  # Exit on any error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🤖 Pi Local Assistant Setup Script${NC}"

# 1. Install System Dependencies
echo -e "${YELLOW}[1/8] Installing System Tools (apt)...${NC}"
sudo apt update
sudo apt install -y \
    python3-tk python3-dev \
    libasound2-dev portaudio19-dev \
    libopenblas-dev liblapack-dev libblas-dev \
    cmake build-essential espeak-ng git

# 2. Create Folders (including faces/capturing)
echo -e "${YELLOW}[2/8] Creating Folders...${NC}"
mkdir -p piper
mkdir -p sounds/greeting_sounds sounds/thinking_sounds sounds/ack_sounds sounds/error_sounds
mkdir -p faces/idle faces/listening faces/thinking faces/speaking faces/error faces/warmup faces/capturing

# 3. Download Piper TTS (aarch64 only)
echo -e "${YELLOW}[3/8] Setting up Piper TTS...${NC}"
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
echo -e "${YELLOW}[4/8] Downloading Voice Model...${NC}"
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
echo -e "${YELLOW}[5/8] Installing Python Libraries...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip

# Force rebuild sounddevice against the newly installed PortAudio dev headers
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
echo -e "${YELLOW}[6/8] Checking Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Ollama not found. Installing...${NC}"
    curl -fsSL https://ollama.ai/install.sh | sh
fi
ollama pull gemma3:1b
ollama pull moondream

# 7. Download Wake Word Model
echo -e "${YELLOW}[7/8] Setting up Wake Word...${NC}"
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
echo -e "${YELLOW}[8/8] Building whisper.cpp (Speech-to-Text engine)...${NC}"
echo -e "${YELLOW}      This step takes 3-5 minutes on Raspberry Pi 5.${NC}"
if [ ! -d "whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git
fi
cd whisper.cpp

# Use cmake (required by modern whisper.cpp releases)
cmake -B build -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
cmake --build build --config Release -j$(nproc)

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
