#!/bin/bash
# verify.sh — Full stack verification for Be More Agent
# Run from project root (with venv active): source venv/bin/activate && bash verify.sh

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0; FAIL=0; WARN=0

pass()   { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
fail()   { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }
warn()   { echo -e "  ${YELLOW}⚠${NC} $1"; WARN=$((WARN+1)); }
header() { echo -e "\n${BOLD}$1${NC}"; }

echo -e "${BOLD}Be More Agent — Stack Verification${NC}"
echo -e "Date: $(date)"

# ─────────────────────────────────────────────────────────────
header "[1/7] Required files"
# ─────────────────────────────────────────────────────────────
[[ -f "whisper.cpp/build/bin/whisper-cli" ]] \
    && pass "whisper-cli binary" \
    || fail "whisper-cli not found — run setup.sh"

[[ -s "whisper.cpp/models/ggml-base.en.bin" ]] \
    && pass "whisper model (ggml-base.en)" \
    || fail "whisper model missing — run setup.sh"

[[ -f "wakeword.onnx" ]] \
    && pass "wakeword.onnx" \
    || fail "wakeword.onnx missing — run setup.sh"

if [[ "$(uname -m)" == "aarch64" ]]; then
    [[ -f "piper/piper" ]] \
        && pass "piper binary" \
        || fail "piper binary missing — run setup.sh"
else
    warn "piper binary check skipped (not aarch64)"
fi

[[ -s "piper/en_GB-semaine-medium.onnx" ]] \
    && pass "piper voice model (.onnx)" \
    || fail "piper voice model missing — run setup.sh"

[[ -s "piper/en_GB-semaine-medium.onnx.json" ]] \
    && pass "piper voice config (.onnx.json)" \
    || fail "piper voice config missing — run setup.sh"

[[ -f "agent.py" ]]      && pass "agent.py"      || fail "agent.py not found"
[[ -f "config.json" ]]   && pass "config.json"   || fail "config.json not found"

# ─────────────────────────────────────────────────────────────
header "[2/7] Python packages"
# ─────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    fail "python3 not found"
else
    pass "python3 ($(python3 --version 2>&1))"
    for pkg in sounddevice numpy scipy openwakeword ollama; do
        python3 -c "import $pkg" 2>/dev/null \
            && pass "$pkg" \
            || fail "$pkg — run: pip install $pkg"
    done
    python3 -c "from duckduckgo_search import DDGS" 2>/dev/null \
        && pass "duckduckgo_search" \
        || fail "duckduckgo_search — run: pip install duckduckgo-search"
    python3 -c "from PIL import Image" 2>/dev/null \
        && pass "Pillow" \
        || fail "Pillow — run: pip install Pillow"
    python3 -c "import wave, struct, subprocess, tkinter" 2>/dev/null \
        && pass "stdlib (wave, struct, subprocess, tkinter)" \
        || fail "stdlib module missing — check Python installation"
fi

# ─────────────────────────────────────────────────────────────
header "[3/7] Ollama"
# ─────────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    fail "ollama not installed — run setup.sh"
else
    pass "ollama installed ($(ollama --version 2>&1 | head -1))"
    if ollama list 2>/dev/null | grep -q "gemma3:1b"; then
        pass "gemma3:1b model present"
    else
        fail "gemma3:1b not pulled — run: ollama pull gemma3:1b"
    fi
    if ollama list 2>/dev/null | grep -q "moondream"; then
        pass "moondream model present"
    else
        warn "moondream not pulled (vision disabled) — run: ollama pull moondream"
    fi
fi

# ─────────────────────────────────────────────────────────────
header "[4/7] Audio devices"
# ─────────────────────────────────────────────────────────────
python3 - > /tmp/bma_devices.txt 2>&1 <<'PYEOF'
import sounddevice as sd, sys
try:
    devices = list(sd.query_devices())
except Exception as e:
    print(f"ERROR:{e}"); sys.exit(1)

for i, d in enumerate(devices):
    ic  = d.get("max_input_channels",  0)
    oc  = d.get("max_output_channels", 0)
    nm  = d.get("name", "")
    usb = "usb" in nm.lower()
    print(f"DEV:{i}|{nm}|{ic}|{oc}|{usb}")

usb_in  = next((i for i,d in enumerate(devices)
                if d.get("max_input_channels",0)>0  and "usb" in d.get("name","").lower()), None)
usb_out = next((i for i,d in enumerate(devices)
                if d.get("max_output_channels",0)>0 and "usb" in d.get("name","").lower()), None)
if usb_in  is not None: print(f"USB_IN:{usb_in}:{devices[usb_in]['name']}")
if usb_out is not None: print(f"USB_OUT:{usb_out}:{devices[usb_out]['name']}")
PYEOF

if grep -q "^ERROR:" /tmp/bma_devices.txt; then
    fail "Audio device query failed: $(grep '^ERROR:' /tmp/bma_devices.txt | cut -d: -f2-)"
else
    echo -e "  Available devices:"
    while IFS='|' read -r idx name ic oc is_usb; do
        usb_tag=""; [[ "$is_usb" == "True" ]] && usb_tag="  [USB]"
        echo -e "    [${idx#DEV:}] ${name}  IN:${ic} OUT:${oc}${usb_tag}"
    done < <(grep "^DEV:" /tmp/bma_devices.txt | sed 's/^DEV://')

    if grep -q "^USB_IN:" /tmp/bma_devices.txt; then
        USB_IN_IDX=$(grep "^USB_IN:" /tmp/bma_devices.txt | cut -d: -f2)
        USB_IN_NAME=$(grep "^USB_IN:" /tmp/bma_devices.txt | cut -d: -f3-)
        pass "USB input: $USB_IN_NAME (device $USB_IN_IDX)"
    else
        warn "No USB input device detected — system default will be used"
    fi

    if grep -q "^USB_OUT:" /tmp/bma_devices.txt; then
        USB_OUT_IDX=$(grep "^USB_OUT:" /tmp/bma_devices.txt | cut -d: -f2)
        USB_OUT_NAME=$(grep "^USB_OUT:" /tmp/bma_devices.txt | cut -d: -f3-)
        pass "USB output: $USB_OUT_NAME (device $USB_OUT_IDX)"
    else
        warn "No USB output device detected — system default will be used"
    fi
fi

# ─────────────────────────────────────────────────────────────
header "[5/7] ALSA mic gain (auto-fix if too low)"
# ─────────────────────────────────────────────────────────────
if ! command -v amixer &>/dev/null; then
    warn "amixer not found — skipping ALSA gain check (install alsa-utils)"
else
    USB_CARD=$(arecord -l 2>/dev/null | grep -i "usb" | grep -oP 'card \K[0-9]+' | head -1)
    if [ -z "$USB_CARD" ]; then
        warn "No USB audio card found via arecord — skipping ALSA gain check"
    else
        echo -e "  USB audio on ALSA card: $USB_CARD"

        # Show all capture-related controls
        CTRL_LIST=$(amixer -c "$USB_CARD" scontrols 2>/dev/null | grep -i "mic\|capture\|gain\|volume")
        if [ -n "$CTRL_LIST" ]; then
            echo -e "  Controls: $(echo "$CTRL_LIST" | tr '\n' ',' | sed 's/,$//')"
        fi

        # Detect current capture volume — flag if any control is below 40%
        LOW=$(amixer -c "$USB_CARD" 2>/dev/null | grep -iE "capture|mic" | grep -E "\[([0-9]|[1-3][0-9])%\]" | head -3)
        if [ -n "$LOW" ]; then
            warn "Capture volume is low — attempting to boost to 80%"
            FIXED=0
            for ctrl in "Mic" "Capture" "Mic Capture Volume" "PCM Capture Volume" \
                        "Mic Boost" "Digital Capture Volume" "Auto Gain Control"; do
                if amixer -c "$USB_CARD" sset "$ctrl" 80% 2>/dev/null | grep -q "%"; then
                    echo -e "    ${GREEN}set '$ctrl' → 80%${NC}"
                    FIXED=1
                fi
            done
            # Turn off Auto Gain Control if present (causes unpredictable levels)
            amixer -c "$USB_CARD" sset "Auto Gain Control" off 2>/dev/null && \
                echo -e "    ${GREEN}disabled Auto Gain Control${NC}"
            [ $FIXED -eq 1 ] && pass "ALSA gain boosted" || warn "Could not adjust gain — use: alsamixer -c $USB_CARD"
        else
            pass "ALSA mic gain looks OK (run 'alsamixer -c $USB_CARD' to adjust manually)"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────
header "[6/7] Microphone input test (3 seconds — speak or make noise)"
# ─────────────────────────────────────────────────────────────
echo -e "  ${YELLOW}Recording in 1 second...${NC}"
sleep 1

python3 - > /tmp/bma_mic_test.txt 2>&1 <<'PYEOF'
import sounddevice as sd, numpy as np, wave, sys
try:
    import scipy.signal as _sig
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

def find_usb(kind):
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(sd.query_devices()):
        if d.get(key, 0) > 0 and "usb" in d.get("name", "").lower():
            return i
    return None

dev  = find_usb("input")
rate = None
for r in [44100, 48000, 32000, 16000]:
    try:
        sd.check_input_settings(device=dev, samplerate=r, channels=1, dtype="int16")
        rate = r; break
    except Exception:
        pass

if rate is None:
    print("RESULT:FAIL:No supported sample rate found for input device")
    sys.exit(1)

print(f"INFO:device={dev} rate={rate}Hz", flush=True)

try:
    data = sd.rec(int(3 * rate), samplerate=rate, channels=1, dtype="int16", device=dev)
    sd.wait()
except Exception as e:
    print(f"RESULT:FAIL:Recording error: {e}")
    sys.exit(1)

flat = data.flatten()
peak = int(np.max(np.abs(flat)))
rms  = float(np.sqrt(np.mean(flat.astype(np.float64) ** 2)))
bars = min(40, peak // 200)
bar  = "#" * bars + "." * (40 - bars)
print(f"LEVEL:peak={peak:5d}  rms={rms:6.1f}  |{bar}|")

if peak < 50:
    print("RESULT:FAIL:No signal (peak<50). Check mic is plugged in and not muted.")
    sys.exit(1)
elif peak < 800:
    print(f"RESULT:WARN:Signal very low (peak={peak}). "
          f"Run: alsamixer and raise Capture/Mic volume, then re-run verify.sh")
else:
    print(f"RESULT:OK:peak={peak}")

# Save as 16kHz WAV for transcription test
try:
    wav_data = flat
    wav_rate = rate
    if rate != 16000:
        if HAS_SCIPY:
            from math import gcd
            g = gcd(rate, 16000)
            wav_data = _sig.resample_poly(flat, 16000 // g, rate // g).astype(np.int16)
        else:
            step = rate / 16000
            idx  = np.arange(0, len(flat), step).astype(int)
            idx  = idx[idx < len(flat)]
            wav_data = flat[idx]
        wav_rate = 16000
    with wave.open("/tmp/bma_verify_audio.wav", "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(wav_rate)
        wf.writeframes(wav_data.tobytes())
    print("WAV_SAVED:/tmp/bma_verify_audio.wav")
except Exception as e:
    print(f"WAV_ERROR:{e}")
PYEOF

MIC_INFO=$(grep   "^INFO:"   /tmp/bma_mic_test.txt | sed 's/^INFO://')
MIC_LEVEL=$(grep  "^LEVEL:"  /tmp/bma_mic_test.txt | sed 's/^LEVEL://')
MIC_RESULT=$(grep "^RESULT:" /tmp/bma_mic_test.txt | sed 's/^RESULT://')
WAV_ERR=$(grep    "^WAV_ERR" /tmp/bma_mic_test.txt)

[[ -n "$MIC_INFO"  ]] && echo -e "  $MIC_INFO"
[[ -n "$MIC_LEVEL" ]] && echo -e "  $MIC_LEVEL"
[[ -n "$WAV_ERR"   ]] && echo -e "  ${YELLOW}$WAV_ERR${NC}"

case "$(echo "$MIC_RESULT" | cut -d: -f1)" in
    OK)   pass "Microphone: $(echo "$MIC_RESULT" | cut -d: -f2-)" ;;
    WARN) warn "Microphone: $(echo "$MIC_RESULT" | cut -d: -f2-)" ;;
    *)    fail "Microphone: $(echo "$MIC_RESULT" | cut -d: -f2-)" ;;
esac

# ─────────────────────────────────────────────────────────────
header "[7/7] Whisper transcription test"
# ─────────────────────────────────────────────────────────────
if [[ ! -f "whisper.cpp/build/bin/whisper-cli" ]]; then
    fail "whisper-cli missing — run setup.sh first"
elif ! grep -q "WAV_SAVED" /tmp/bma_mic_test.txt 2>/dev/null; then
    warn "Skipped — no recorded audio (mic test failed)"
else
    WAV_FILE=$(grep "^WAV_SAVED:" /tmp/bma_mic_test.txt | cut -d: -f2)
    echo -e "  Running whisper on recorded audio..."
    WHISPER_OUT=$(./whisper.cpp/build/bin/whisper-cli \
        -m whisper.cpp/models/ggml-base.en.bin \
        -l en -t 4 -f "$WAV_FILE" 2>&1)
    TRANSCRIPT=$(echo "$WHISPER_OUT" | grep -E '\[[0-9:. ]+-->' | tail -3 | sed 's/.*\] //' | tr '\n' ' ')
    if [[ -n "$TRANSCRIPT" ]]; then
        pass "Transcription: \"$(echo "$TRANSCRIPT" | xargs)\""
    else
        # whisper printed something but no timestamp lines — show raw tail
        RAW=$(echo "$WHISPER_OUT" | tail -3 | tr '\n' ' ')
        warn "No timestamped output. Whisper said: \"$RAW\""
        warn "(This is OK if you were silent — speak during the mic test to verify)"
    fi
fi

# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}✓ Passed: $PASS${NC}   ${RED}✗ Failed: $FAIL${NC}   ${YELLOW}⚠ Warnings: $WARN${NC}"
if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}  ✨ All checks passed — stack is ready!${NC}"
    echo -e "  Run:  source venv/bin/activate && python agent.py"
    exit 0
else
    echo -e "${RED}  ❌ $FAIL check(s) failed — fix the issues above before running agent.py${NC}"
    exit 1
fi
