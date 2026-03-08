# =========================================================================
#  Be More Agent 🤖
#  A Local, Offline-First AI Agent for Raspberry Pi
#
#  Copyright (c) 2026 brenpoly
#  Licensed under the MIT License
#  Source: https://github.com/brenpoly/be-more-agent
#
#  DISCLAIMER:
#  This software is provided "as is", without warranty of any kind.
#  This project is a generic framework and includes no copyrighted assets.
# =========================================================================

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import json
import os
import subprocess
import random
import re
import sys
import select
import traceback
import atexit
import datetime
import warnings
import wave
import struct 

# Suppress harmless library warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

# Core dependencies
import sounddevice as sd
import numpy as np
import scipy.signal 

# --- AI ENGINES ---
import openwakeword
from openwakeword.model import Model
import ollama 

# --- WEB SEARCH (Using your working import) ---
from duckduckgo_search import DDGS

# =========================================================================
# 1. CONFIGURATION & CONSTANTS
# =========================================================================

CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"
BMO_IMAGE_FILE = "current_image.jpg"
# Resolved after config is loaded — see below DEFAULT_CONFIG block
WAKE_WORD_MODEL     = None
WAKE_WORD_THRESHOLD = None

# HARDWARE SETTINGS

DEFAULT_CONFIG = {
    # Models
    "text_model":           "gemma3:1b",
    "vision_model":         "moondream",
    "voice_model":          "piper/en_GB-semaine-medium.onnx",
    # Personality
    "system_prompt_extras": "",
    "chat_memory":          True,
    # Wake word
    "wake_word_model":      "./wakeword.onnx",
    "wake_word_threshold":  0.5,    # 0.3 = more sensitive, 0.7 = stricter
    # Recording
    "silence_to_stop":      1.5,    # seconds of post-speech silence before cutting off
    # Transcription
    "whisper_language":     "en",   # language code: en, de, fr, es, ...
    "whisper_threads":      4,
    # LLM
    "llm_temperature":      0.7,
    "llm_threads":          4,
    # Hardware
    "camera_rotation":      0,
    "input_device":         None,
    "input_sample_rate":    None,
    "output_device":        None,
}

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"Config Error: {e}. Using defaults.")
    return config

CURRENT_CONFIG = load_config()
TEXT_MODEL          = CURRENT_CONFIG["text_model"]
VISION_MODEL        = CURRENT_CONFIG["vision_model"]
WAKE_WORD_MODEL     = CURRENT_CONFIG["wake_word_model"]
WAKE_WORD_THRESHOLD = float(CURRENT_CONFIG["wake_word_threshold"])

OLLAMA_OPTIONS = {
    'keep_alive': '-1',
    'num_thread': int(CURRENT_CONFIG["llm_threads"]),
    'temperature': float(CURRENT_CONFIG["llm_temperature"]),
    'top_k': 40,
    'top_p': 0.9,
}

def _query_devices_safe():
    try:
        return list(sd.query_devices())
    except Exception as e:
        print(f"[AUDIO] Device query failed: {e}", flush=True)
        return []


def find_usb_audio_device(kind="input"):
    """Return the index of the first USB audio device for the given kind ('input'/'output'), or None."""
    ch_key = "max_input_channels" if kind == "input" else "max_output_channels"
    for idx, dev in enumerate(_query_devices_safe()):
        if dev.get(ch_key, 0) > 0 and "usb" in dev.get("name", "").lower():
            return idx
    return None


def print_audio_devices(input_idx, output_idx):
    """Print a table of all audio devices, highlighting the selected ones."""
    devices = _query_devices_safe()
    if not devices:
        return
    print("[AUDIO] Available devices:", flush=True)
    for idx, dev in enumerate(devices):
        ic = dev.get("max_input_channels", 0)
        oc = dev.get("max_output_channels", 0)
        tags = ""
        if idx == input_idx:
            tags += "  <-- INPUT"
        if idx == output_idx:
            tags += "  <-- OUTPUT"
        print(f"  [{idx:2d}] {dev['name']:<40} IN:{ic}  OUT:{oc}{tags}", flush=True)


def resolve_input_device(config):
    """Resolve audio input device: explicit config > USB auto-detect > system default."""
    requested = config.get("input_device")
    devices = _query_devices_safe()

    if requested not in (None, "", "default"):
        if isinstance(requested, int) or (isinstance(requested, str) and requested.isdigit()):
            index = int(requested)
            if 0 <= index < len(devices):
                return index
            print(f"[AUDIO] Input device index {index} out of range, falling back to USB auto-detect.", flush=True)
        else:
            requested_lower = str(requested).lower()
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0 and requested_lower in dev.get("name", "").lower():
                    return idx
            print(f"[AUDIO] Input device '{requested}' not found, falling back to USB auto-detect.", flush=True)

    # Auto-detect USB microphone
    usb = find_usb_audio_device("input")
    if usb is not None:
        return usb

    return None  # system default


def resolve_output_device(config):
    """Resolve audio output device: explicit config > USB auto-detect > system default."""
    requested = config.get("output_device")
    devices = _query_devices_safe()

    if requested not in (None, "", "default"):
        if isinstance(requested, int) or (isinstance(requested, str) and requested.isdigit()):
            index = int(requested)
            if 0 <= index < len(devices):
                return index
            print(f"[AUDIO] Output device index {index} out of range, falling back to USB auto-detect.", flush=True)
        else:
            requested_lower = str(requested).lower()
            for idx, dev in enumerate(devices):
                if dev.get("max_output_channels", 0) > 0 and requested_lower in dev.get("name", "").lower():
                    return idx
            print(f"[AUDIO] Output device '{requested}' not found, falling back to USB auto-detect.", flush=True)

    # Auto-detect USB speaker
    usb = find_usb_audio_device("output")
    if usb is not None:
        return usb

    return None  # system default


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
OUTPUT_DEVICE_NAME = resolve_output_device(CURRENT_CONFIG)
print_audio_devices(INPUT_DEVICE_NAME, OUTPUT_DEVICE_NAME)

def _device_label(idx):
    if idx is None:
        return "system default"
    try:
        return sd.query_devices(idx)["name"]
    except Exception:
        return str(idx)

print(f"[AUDIO] Input  → {_device_label(INPUT_DEVICE_NAME)}", flush=True)
print(f"[AUDIO] Output → {_device_label(OUTPUT_DEVICE_NAME)}", flush=True)


class BotStates:
    IDLE = "idle"             
    LISTENING = "listening"   
    THINKING = "thinking"     
    SPEAKING = "speaking"     
    ERROR = "error"           
    CAPTURING = "capturing" 
    WARMUP = "warmup"       

# --- SYSTEM PROMPT ---
BASE_SYSTEM_PROMPT = """You are a helpful robot assistant running on a Raspberry Pi.
Personality: Cute, helpful, robot.
Style: Short sentences. Enthusiastic.

INSTRUCTIONS:
- If the user asks for a physical action (time, search, photo), output JSON.
- If the user just wants to chat, reply with NORMAL TEXT.

### EXAMPLES ###

User: What time is it?
You: {"action": "get_time", "value": "now"}

User: Hello!
You: Hi! I am ready to help!

User: Search for news about robots.
You: {"action": "search_web", "value": "robots news"}

User: What do you see right now?
You: {"action": "capture_image", "value": "environment"}

### END EXAMPLES ###
"""

SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + "\n\n" + CURRENT_CONFIG.get("system_prompt_extras", "")

# Sound Directories
greeting_sounds_dir = "sounds/greeting_sounds"
ack_sounds_dir = "sounds/ack_sounds"
thinking_sounds_dir = "sounds/thinking_sounds"
error_sounds_dir = "sounds/error_sounds"

# =========================================================================
# 2. GUI CLASS
# =========================================================================

class BotGUI:
    BG_WIDTH, BG_HEIGHT = 800, 480 
    OVERLAY_WIDTH, OVERLAY_HEIGHT = 400, 300 

    def __init__(self, master):
        self.master = master
        master.title("Pi Assistant")
        master.attributes('-fullscreen', True) 
        master.bind('<Escape>', self.exit_fullscreen)
        
        # Inputs
        master.bind('<Return>', self.handle_ptt_toggle)
        master.bind('<space>', self.handle_speaking_interrupt)
        atexit.register(self.safe_exit)
        
        # State
        self.current_state = BotStates.WARMUP
        self.current_volume = 0 
        self.animations = {}
        self.current_frame_index = 0
        self.current_overlay_image = None
        
        self.permanent_memory = self.load_chat_history()
        self.session_memory = []
        self.thinking_sound_active = threading.Event()
        
        self.last_ptt_time = 0 
        self.ptt_event = threading.Event()       
        self.recording_active = threading.Event() 
        self.interrupted = threading.Event() 
        
        self.tts_queue = []          
        self.tts_queue_lock = threading.Lock() 
        self.tts_thread = None       
        self.tts_active = threading.Event()
        self.current_audio_process = None
        self.exiting = False

        # --- WAKE WORD INITIALIZATION ---
        print("[INIT] Loading Wake Word...", flush=True)
        self.oww_model = None
        if os.path.exists(WAKE_WORD_MODEL):
            try:
                self.oww_model = Model(wakeword_model_paths=[WAKE_WORD_MODEL])
                print("[INIT] Wake Word Loaded.", flush=True)
            except TypeError:
                try:
                    self.oww_model = Model(wakeword_models=[WAKE_WORD_MODEL])
                    print("[INIT] Wake Word Loaded (New API).", flush=True)
                except Exception as e:
                    print(f"[CRITICAL] Failed to load model: {e}")
            except Exception as e:
                print(f"[CRITICAL] Failed to load model: {e}")
        else:
            print(f"[CRITICAL] Model not found: {WAKE_WORD_MODEL}")

        # GUI Setup
        self.background_label = tk.Label(master)
        self.background_label.place(x=0, y=0, width=self.BG_WIDTH, height=self.BG_HEIGHT)
        self.background_label.bind('<Button-1>', self.toggle_hud_visibility) 
        
        self.overlay_label = tk.Label(master, bg='black')
        self.overlay_label.bind('<Button-1>', self.toggle_hud_visibility)
        
        self.response_text = tk.Text(master, height=6, width=60, wrap=tk.WORD, 
                                     state=tk.DISABLED, bg="#ffffff", fg="#000000", font=('Arial', 12)) 
        
        self.status_var = tk.StringVar(value="Initializing...")
        self.status_label = ttk.Label(master, textvariable=self.status_var, background="#2e2e2e", foreground="white")
        
        self.exit_button = ttk.Button(master, text="Exit & Save", command=self.safe_exit)

        self.load_animations()
        self.update_animation() 
        
        threading.Thread(target=self.safe_main_execution, daemon=True).start()

    # --- HELPERS ---

    def extract_json_from_text(self, text):
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return None
        except: return None

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
        
    def exit_fullscreen(self, event=None):
        self.master.attributes('-fullscreen', False)
        self.safe_exit()

    def toggle_hud_visibility(self, event=None):
        try:
            if self.response_text.winfo_ismapped():
                self.response_text.place_forget()
                self.status_label.place_forget()
                self.exit_button.place_forget()
            else:
                self.response_text.place(relx=0.5, rely=0.82, anchor=tk.S)
                self.status_label.place(relx=0.5, rely=1.0, anchor=tk.S, relwidth=1)
                self.exit_button.place(x=10, y=10)
        except tk.TclError: pass

    def handle_ptt_toggle(self, event=None):
        current_time = time.time()
        if current_time - self.last_ptt_time < 0.5: 
            return 
        self.last_ptt_time = current_time

        if self.recording_active.is_set():
            print("[PTT] Toggle OFF", flush=True)
            self.recording_active.clear() 
        else:
            if self.current_state == BotStates.IDLE or "Wait" in self.status_var.get():
                print("[PTT] Toggle ON", flush=True)
                self.recording_active.set() 
                self.ptt_event.set()

    def handle_speaking_interrupt(self, event=None):
        if self.current_state == BotStates.SPEAKING or self.current_state == BotStates.THINKING:
            self.interrupted.set()
            self.thinking_sound_active.clear()
            with self.tts_queue_lock:
                self.tts_queue.clear()
            if self.current_audio_process:
                try: self.current_audio_process.terminate()
                except: pass
            self.set_state(BotStates.IDLE, "Interrupted.")

    def load_animations(self):
        base_path = "faces"
        states = ["idle", "listening", "thinking", "speaking", "error", "capturing", "warmup"] 
        for state in states:
            folder = os.path.join(base_path, state)
            self.animations[state] = []
            if os.path.exists(folder):
                files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.png')])
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize((self.BG_WIDTH, self.BG_HEIGHT))
                    self.animations[state].append(ImageTk.PhotoImage(img))
            if not self.animations[state]:
                if state in self.animations.get("idle", []):
                     self.animations[state] = self.animations["idle"]
                else:
                    # Blue screen fallback
                    blank = Image.new('RGB', (self.BG_WIDTH, self.BG_HEIGHT), color='#0000FF')
                    self.animations[state].append(ImageTk.PhotoImage(blank))

    def update_animation(self):
        frames = self.animations.get(self.current_state, []) or self.animations.get(BotStates.IDLE, [])
        if not frames:
            self.master.after(500, self.update_animation)
            return

        if self.current_state == BotStates.SPEAKING:
            if len(frames) > 1:
                self.current_frame_index = random.randint(1, len(frames) - 1)
            else:
                self.current_frame_index = 0 
        else:
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

        self.background_label.config(image=frames[self.current_frame_index])
        
        speed = 50 if self.current_state == BotStates.SPEAKING else 500
        self.master.after(speed, self.update_animation)

    def set_state(self, state, msg="", cam_path=None):
        def _update():
            if msg: print(f"[STATE] {state.upper()}: {msg}", flush=True)
            if self.current_state != state:
                self.current_state = state
                self.current_frame_index = 0
            if msg: self.status_var.set(msg)
            if cam_path and os.path.exists(cam_path) and state in [BotStates.THINKING, BotStates.SPEAKING]:
                try:
                    img = Image.open(cam_path).resize((self.OVERLAY_WIDTH, self.OVERLAY_HEIGHT))
                    self.current_overlay_image = ImageTk.PhotoImage(img)
                    self.overlay_label.config(image=self.current_overlay_image)
                    self.overlay_label.place(x=200, y=90)
                except: pass
            else:
                self.overlay_label.place_forget()
        self.master.after(0, _update)

    def append_to_text(self, text, newline=True):
        def _update():
            self.response_text.config(state=tk.NORMAL)
            if newline: 
                self.response_text.insert(tk.END, text + "\n")
            else: 
                self.response_text.insert(tk.END, text)
            
            self.response_text.see(tk.END)
            self.response_text.config(state=tk.DISABLED)
            
        self.master.after(0, _update)

    def _stream_to_text(self, chunk):
        def update_text_stream():
            self.response_text.config(state=tk.NORMAL)
            self.response_text.insert(tk.END, chunk)
            self.response_text.see(tk.END) 
            self.response_text.config(state=tk.DISABLED)
        self.master.after(0, update_text_stream)

    # =========================================================================
    # 3. ACTION ROUTER
    # =========================================================================
    
    def execute_action_and_get_result(self, action_data):
        raw_action = action_data.get("action", "").lower().strip()
        value = action_data.get("value") or action_data.get("query")
        
        VALID_TOOLS = {
            "get_time", "search_web", "capture_image"
        }
        
        ALIASES = {
            "google": "search_web", "browser": "search_web", "news": "search_web",         
            "search_news": "search_web", "look": "capture_image", "see": "capture_image", 
            "check_time": "get_time"
        }

        action = ALIASES.get(raw_action, raw_action)
        print(f"ACTION: {raw_action} -> {action}", flush=True)

        if action not in VALID_TOOLS:
            if value and isinstance(value, str) and len(value.split()) > 1:
                return f"CHAT_FALLBACK::{value}"
            return "INVALID_ACTION"

        if action == "get_time":
            now = datetime.datetime.now().strftime("%I:%M %p")
            return f"The current time is {now}."
        
        elif action == "search_web":
            print(f"Searching web for: {value}...", flush=True)
            try:
                # 'us-en' region is often more stable for CLI queries
                with DDGS() as ddgs:
                    results = []
                    # 1. News search
                    try:
                        results = list(ddgs.news(value, region='us-en', max_results=1))
                        if results: 
                            print(f"[DEBUG] Found News: {results[0].get('title')}", flush=True)
                    except Exception as e: 
                        print(f"[DEBUG] News Search Error: {e}", flush=True)
                    
                    # 2. Text fallback
                    if not results:
                        print("[DEBUG] No news found, trying text search...", flush=True)
                        try: 
                            results = list(ddgs.text(value, region='us-en', max_results=1))
                            if results: 
                                print(f"[DEBUG] Found Text: {results[0].get('title')}", flush=True)
                        except Exception as e:
                             print(f"[DEBUG] Text Search Error: {e}", flush=True)

                    if results:
                        r = results[0]
                        # Safe get
                        title = r.get('title', 'No Title')
                        body = r.get('body', r.get('snippet', 'No Body'))
                        return f"SEARCH RESULTS for '{value}':\nTitle: {title}\nSnippet: {body[:300]}"
                    else: 
                        print(f"[DEBUG] Search returned 0 results.", flush=True)
                        return "SEARCH_EMPTY"
            except Exception as e:
                print(f"[DEBUG] Connection/Library Error: {e}", flush=True)
                return "SEARCH_ERROR"
        
        elif action == "capture_image":
             return "IMAGE_CAPTURE_TRIGGERED"

        return None

    # =========================================================================
    # 4. CORE LOGIC
    # =========================================================================

    def safe_main_execution(self):
        try:
            self.warm_up_logic()
            self.tts_active.set()
            self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self.tts_thread.start()
            
            while True:
                trigger_source = self.detect_wake_word_or_ptt()
                if self.interrupted.is_set():
                    self.interrupted.clear()
                    self.set_state(BotStates.IDLE, "Resetting...")
                    continue

                self.set_state(BotStates.LISTENING, "I'm listening!")
                
                audio_file = None
                if trigger_source == "PTT":
                    audio_file = self.record_voice_ptt()
                else:
                    audio_file = self.record_voice_adaptive()
                
                if not audio_file: 
                    self.set_state(BotStates.IDLE, "Heard nothing.")
                    continue
                
                user_text = self.transcribe_audio(audio_file)
                if not user_text:
                    self.set_state(BotStates.IDLE, "Transcription empty.")
                    continue
                
                self.append_to_text(f"YOU: {user_text}")
                self.interrupted.clear()
                self.chat_and_respond(user_text, img_path=None)
                    
        except Exception as e:
            traceback.print_exc()
            self.set_state(BotStates.ERROR, f"Fatal Error: {str(e)[:40]}")

    def warm_up_logic(self):
        self.set_state(BotStates.WARMUP, "Warming up brains...")
        try:
            ollama.generate(model=TEXT_MODEL, prompt="", keep_alive=-1)
        except Exception as e:
            print(f"Failed to load {TEXT_MODEL}: {e}", flush=True)
        self.play_sound(self.get_random_sound(greeting_sounds_dir))
        print("Models loaded.", flush=True)

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

        fallback_kwargs = {**stream_kwargs, "blocksize": 1024, "latency": "high"}

        for attempt, kwargs in enumerate([stream_kwargs, fallback_kwargs]):
            try:
                result = self._wake_word_listen_loop(kwargs, CHUNK_SIZE, use_resampling or attempt > 0)
                if result is not None:
                    return result  # "PTT" or "CLI"
                return "WAKE"
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
        Inner wake word listen loop.
        Returns "PTT", "CLI", or None (None means wake word triggered).
        Raises on unrecoverable stream error so caller can retry with fallback settings.
        """
        MAX_CONSECUTIVE_OVERFLOWS = 5
        overflow_count = 0
        _debug_tick = 0

        print(f"[WAKE] Listening on device={stream_kwargs.get('device')} "
              f"rate={stream_kwargs['samplerate']} blocksize={stream_kwargs.get('blocksize')}", flush=True)

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

                peak = int(np.max(np.abs(audio_data))) if len(audio_data) > 0 else 0
                _debug_tick += 1
                if _debug_tick % 150 == 0:
                    bar = "#" * min(40, peak // 200)
                    print(f"[MIC] peak={peak:5d} |{bar:<40}|", flush=True)

                # Skip prediction on silence to save CPU
                if peak < 200:
                    continue

                prediction = self.oww_model.predict(audio_data)
                for mdl in self.oww_model.prediction_buffer.keys():
                    score = list(self.oww_model.prediction_buffer[mdl])[-1]
                    if score > WAKE_WORD_THRESHOLD:
                        print(f"[WAKE] Triggered on '{mdl}' with score: {score:.2f}", flush=True)
                        self.oww_model.reset()
                        return None  # Wake word triggered

    def record_voice_adaptive(self, filename="input.wav"):
        """
        Record until the user stops speaking.

        Pipeline:
          1. Calibrate noise floor (0.3 s of pre-speech audio).
          2. Set speech threshold = max(0.03, noise_floor * 4).
          3. Wait up to MAX_WAIT_FOR_SPEECH seconds for the user to start.
          4. Once speech is detected, stop after SILENCE_TO_STOP consecutive
             seconds of silence — giving a natural pause window.
        """
        MAX_WAIT_FOR_SPEECH = 8.0   # give up if no speech starts within 8 s
        SILENCE_TO_STOP     = float(CURRENT_CONFIG.get("silence_to_stop", 1.5))
        MAX_RECORD_TIME     = 30.0  # hard cap regardless
        MIN_SPEECH_SECS     = 0.3   # must capture at least this much speech
        CALIBRATION_SECS    = 0.3   # how long to measure background noise
        MIN_THRESHOLD       = 0.03  # absolute floor — handles very quiet rooms

        samplerate = choose_input_samplerate(INPUT_DEVICE_NAME, CURRENT_CONFIG.get("input_sample_rate"))
        chunk_size = int(samplerate * 0.05)   # 50 ms chunks
        chunk_dur  = chunk_size / samplerate

        # ── Step 1: calibrate noise floor ─────────────────────────────────
        try:
            sd.stop()
            time.sleep(0.1)
            noise_data = sd.rec(int(samplerate * CALIBRATION_SECS),
                                samplerate=samplerate, channels=1,
                                dtype="float32", device=INPUT_DEVICE_NAME)
            sd.wait()
            noise_rms = float(np.sqrt(np.mean(noise_data ** 2)))
        except Exception:
            noise_rms = 0.005  # safe fallback

        speech_threshold = max(MIN_THRESHOLD, noise_rms * 4.0)
        print(f"[AUDIO] Noise RMS={noise_rms:.4f}  →  speech threshold={speech_threshold:.4f}", flush=True)

        # ── Step 2: record with adaptive stop ─────────────────────────────
        buffer         = []
        speech_secs    = 0.0
        silence_secs   = 0.0
        speech_started = False
        stop_event     = threading.Event()

        def callback(indata, frames, time_info, status):
            nonlocal speech_secs, silence_secs, speech_started
            buffer.append(indata.copy())
            rms = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))
            if rms >= speech_threshold:
                speech_started = True
                speech_secs   += chunk_dur
                silence_secs   = 0.0
            elif speech_started:
                silence_secs += chunk_dur
                if silence_secs >= SILENCE_TO_STOP and speech_secs >= MIN_SPEECH_SECS:
                    stop_event.set()

        try:
            time.sleep(0.1)
            start = time.time()
            with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32",
                                callback=callback, device=INPUT_DEVICE_NAME,
                                blocksize=chunk_size):
                print("Recording (Adaptive) — speak now...", flush=True)
                while not stop_event.is_set():
                    elapsed = time.time() - start
                    if elapsed >= MAX_RECORD_TIME:
                        break
                    if not speech_started and elapsed >= MAX_WAIT_FOR_SPEECH:
                        print("[AUDIO] No speech detected within timeout.", flush=True)
                        return None
                    sd.sleep(50)
        except Exception as e:
            print(f"[AUDIO ERROR] Adaptive recording failed: {e}", flush=True)
            return None

        total = len(buffer) * chunk_dur
        print(f"[AUDIO] Done — {total:.1f}s total, "
              f"speech={speech_secs:.1f}s, post-speech silence={silence_secs:.1f}s", flush=True)

        if not speech_started:
            print("[AUDIO] No speech captured.", flush=True)
            return None

        return self.save_audio_buffer(buffer, filename, samplerate)

    def record_voice_ptt(self, filename="input.wav"):
        print("Recording (PTT)...", flush=True)
        time.sleep(0.5)
        samplerate = choose_input_samplerate(INPUT_DEVICE_NAME, CURRENT_CONFIG.get("input_sample_rate"))

        buffer = []
        def callback(indata, frames, time_info, status): buffer.append(indata.copy())

        try:
            sd.stop()
            time.sleep(0.2)
            with sd.InputStream(samplerate=samplerate, channels=1, callback=callback, device=INPUT_DEVICE_NAME):
                while self.recording_active.is_set():
                    sd.sleep(50)
        except Exception as e:
            print(f"[AUDIO ERROR] PTT recording failed: {e}", flush=True)
            return None
            
        return self.save_audio_buffer(buffer, filename, samplerate)

    def save_audio_buffer(self, buffer, filename, samplerate=16000):
        if not buffer: return None
        audio_data = np.concatenate(buffer, axis=0).flatten()
        audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)

        duration = len(audio_data) / samplerate
        peak = float(np.max(np.abs(audio_data)))
        print(f"[AUDIO] Captured {duration:.1f}s at {samplerate}Hz, peak={peak:.4f}", flush=True)

        # Resample to 16kHz — whisper.cpp requires 16kHz input
        # resample_poly uses polyphase FIR with antialiasing: much better quality than resample()
        TARGET_RATE = 16000
        if samplerate != TARGET_RATE:
            from math import gcd
            g = gcd(samplerate, TARGET_RATE)
            audio_data = scipy.signal.resample_poly(audio_data, TARGET_RATE // g, samplerate // g)
            print(f"[AUDIO] Resampled {samplerate}Hz → {TARGET_RATE}Hz ({len(audio_data)} samples)", flush=True)
            samplerate = TARGET_RATE

        if peak < 0.001:
            print("[AUDIO] WARNING: audio is nearly silent — check mic connection and volume", flush=True)

        audio_data = (audio_data * 32767).astype(np.int16)
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(audio_data.tobytes())
        self.play_sound(self.get_random_sound(ack_sounds_dir))
        return filename

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
            lang    = CURRENT_CONFIG.get("whisper_language", "en")
            threads = str(int(CURRENT_CONFIG.get("whisper_threads", 4)))
            result = subprocess.run(
                [WHISPER_BIN, "-m", WHISPER_MODEL, "-l", lang, "-t", threads, "-f", filename],
                capture_output=True, text=True, timeout=60
            )

            if result.returncode != 0:
                error_detail = (result.stderr or result.stdout or "no output").strip()[:200]
                print(f"[ERROR] Whisper failed (code {result.returncode}): {error_detail}", flush=True)
                return ""

            # Some whisper.cpp builds write transcription to stderr; check both
            output = (result.stdout + result.stderr).strip()

            # Collect text from ALL timestamped lines e.g. "[00:00:00 --> 00:00:03]  hello there"
            parts = []
            for line in output.split('\n'):
                line = line.strip()
                if ']' in line:
                    text = line.split(']', 1)[-1].strip()
                    if text:
                        parts.append(text)
            transcription = ' '.join(parts).strip()

            # Fallback: last non-empty line (some builds omit timestamps)
            if not transcription:
                transcription = next(
                    (l.strip() for l in reversed(output.split('\n')) if l.strip()), ""
                )

            print(f"Heard: '{transcription}'", flush=True)
            return transcription

        except subprocess.TimeoutExpired:
            print("[ERROR] Whisper timed out after 60 seconds.", flush=True)
            return ""
        except Exception as e:
            print(f"[ERROR] Transcription error: {e}", flush=True)
            return ""

    def capture_image(self):
        self.set_state(BotStates.CAPTURING, "Watching...")
        try:
            subprocess.run(["rpicam-still", "-t", "500", "-n", "--width", "640", "--height", "480", "-o", BMO_IMAGE_FILE], check=True)
            rotation = CURRENT_CONFIG.get("camera_rotation", 0)
            if rotation != 0:
                img = Image.open(BMO_IMAGE_FILE)
                img = img.rotate(rotation, expand=True) 
                img.save(BMO_IMAGE_FILE)
            return BMO_IMAGE_FILE
        except Exception as e:
            print(f"Camera Error: {e}")
            return None

    # =========================================================================
    # 5. CHAT & RESPOND
    # =========================================================================

    def chat_and_respond(self, text, img_path=None):
        if "forget everything" in text.lower() or "reset memory" in text.lower():
            self.session_memory = []
            self.permanent_memory = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.save_chat_history()
            with self.tts_queue_lock: 
                self.tts_queue.append("Okay. Memory wiped.")
            self.set_state(BotStates.IDLE, "Memory Wiped")
            return

        model_to_use = VISION_MODEL if img_path else TEXT_MODEL
        self.set_state(BotStates.THINKING, "Thinking...", cam_path=img_path)
        
        messages = []
        if img_path:
            messages = [{"role": "user", "content": text, "images": [img_path]}]
        else:
            user_msg = {"role": "user", "content": text}
            messages = self.permanent_memory + self.session_memory + [user_msg]
        
        self.thinking_sound_active.set()
        threading.Thread(target=self._run_thinking_sound_loop, daemon=True).start()
        
        full_response_buffer = ""
        sentence_buffer = "" 
        
        try:
            stream = ollama.chat(model=model_to_use, messages=messages, stream=True, options=OLLAMA_OPTIONS)
            
            is_action_mode = False
            
            for chunk in stream:
                if self.interrupted.is_set(): break 
                content = chunk['message']['content']
                full_response_buffer += content
                
                if '{"' in content or "action:" in content.lower():
                    is_action_mode = True
                    self.thinking_sound_active.clear()
                    continue 

                if is_action_mode: continue

                self.thinking_sound_active.clear()
                if self.current_state != BotStates.SPEAKING:
                    self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                    self.append_to_text("BOT: ", newline=False)

                self._stream_to_text(content)
                
                sentence_buffer += content
                if any(punct in content for punct in ".!?\n"):
                    clean_sentence = sentence_buffer.strip()
                    if clean_sentence and re.search(r'[a-zA-Z0-9]', clean_sentence):
                        with self.tts_queue_lock: self.tts_queue.append(clean_sentence)
                    sentence_buffer = ""

            if is_action_mode:
                action_data = self.extract_json_from_text(full_response_buffer)
                if action_data:
                    tool_result = self.execute_action_and_get_result(action_data)

                    if tool_result and tool_result.startswith("CHAT_FALLBACK::"):
                        chat_text = tool_result.split("::", 1)[1]
                        self.thinking_sound_active.clear()
                        self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                        self.append_to_text("BOT: ", newline=False)
                        self.append_to_text(chat_text, newline=True)
                        with self.tts_queue_lock: self.tts_queue.append(chat_text)
                        self.session_memory.append({"role": "assistant", "content": chat_text})
                        self.wait_for_tts()
                        self.set_state(BotStates.IDLE, "Ready")
                        return

                    if tool_result == "IMAGE_CAPTURE_TRIGGERED":
                        new_img_path = self.capture_image()
                        if new_img_path:
                            self.chat_and_respond(text, img_path=new_img_path)
                            return 

                    elif tool_result == "INVALID_ACTION":
                        fallback_text = "I am not sure how to do that."
                        self.thinking_sound_active.clear()
                        self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                        self.append_to_text("BOT: ", newline=False)
                        self.append_to_text(fallback_text, newline=True)
                        with self.tts_queue_lock: self.tts_queue.append(fallback_text)

                    elif tool_result == "SEARCH_EMPTY":
                        fallback_text = "I searched, but I couldn't find any news about that."
                        self.thinking_sound_active.clear()
                        self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                        self.append_to_text("BOT: ", newline=False)
                        self.append_to_text(fallback_text, newline=True)
                        with self.tts_queue_lock: self.tts_queue.append(fallback_text)

                    elif tool_result == "SEARCH_ERROR":
                        fallback_text = "I cannot reach the internet right now."
                        self.thinking_sound_active.clear()
                        self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                        self.append_to_text("BOT: ", newline=False)
                        self.append_to_text(fallback_text, newline=True)
                        with self.tts_queue_lock: self.tts_queue.append(fallback_text)

                    elif tool_result:
                        summary_prompt = [
                            {"role": "system", "content": "Summarize this result in one short sentence."},
                            {"role": "user", "content": f"RESULT: {tool_result}\nUser Question: {text}"}
                        ]
                        
                        self.set_state(BotStates.THINKING, "Reading...")
                        self.thinking_sound_active.set()
                        
                        final_resp = ollama.chat(model=model_to_use, messages=summary_prompt, stream=False, options=OLLAMA_OPTIONS)
                        final_text = final_resp['message']['content']
                        
                        self.thinking_sound_active.clear()
                        self.set_state(BotStates.SPEAKING, "Speaking...", cam_path=img_path)
                        
                        self.append_to_text("BOT: ", newline=False)
                        self.append_to_text(final_text, newline=True)
                        with self.tts_queue_lock: self.tts_queue.append(final_text)
                        self.session_memory.append({"role": "assistant", "content": final_text})
            else:
                self.append_to_text("")
                self.session_memory.append({"role": "assistant", "content": full_response_buffer}) 
            
            self.wait_for_tts()
            self.set_state(BotStates.IDLE, "Ready")
                
        except Exception as e:
            print(f"LLM Error: {e}")
            self.set_state(BotStates.ERROR, "Brain Freeze!")

    def wait_for_tts(self):
        while self.tts_queue or self.tts_active.is_set():
            if self.interrupted.is_set(): break
            time.sleep(0.1)

    def _tts_worker(self):
        while True:
            text = None
            with self.tts_queue_lock:
                if self.tts_queue: 
                    text = self.tts_queue.pop(0)
                    self.tts_active.set() 
            if text: 
                self.speak(text)
                self.tts_active.clear() 
            else: time.sleep(0.05)

    def speak(self, text):
        clean = re.sub(r"[^\w\s,.!?:-]", "", text)
        if not clean.strip(): return
        
        print(f"[PIPER SPEAKING] '{clean}'", flush=True)
        voice_model = CURRENT_CONFIG.get("voice_model", "piper/en_GB-semaine-medium.onnx")
        
        try:
            self.current_audio_process = subprocess.Popen(
                ["./piper/piper", "--model", voice_model, "--output-raw"], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            self.current_audio_process.stdin.write(clean.encode() + b'\n')
            self.current_audio_process.stdin.close() 

            try:
                device_info = sd.query_devices(OUTPUT_DEVICE_NAME if OUTPUT_DEVICE_NAME is not None else sd.default.device[1])
                native_rate = int(device_info['default_samplerate'])
            except Exception:
                native_rate = 48000

            PIPER_RATE = 22050
            use_native_rate = False

            try:
                sd.check_output_settings(device=OUTPUT_DEVICE_NAME, samplerate=PIPER_RATE)
            except Exception:
                use_native_rate = True

            print(f"[PIPER] Output device={_device_label(OUTPUT_DEVICE_NAME)} "
                  f"rate={native_rate if use_native_rate else PIPER_RATE}", flush=True)

            with sd.RawOutputStream(samplerate=native_rate if use_native_rate else PIPER_RATE,
                                    channels=1, dtype='int16',
                                    device=OUTPUT_DEVICE_NAME, latency='low', blocksize=2048) as stream:
                while True:
                    if self.interrupted.is_set(): break
                    data = self.current_audio_process.stdout.read(4096)
                    if not data: break 
                    
                    audio_chunk = np.frombuffer(data, dtype=np.int16)
                    if len(audio_chunk) > 0:
                        self.current_volume = np.max(np.abs(audio_chunk))
                        if use_native_rate:
                            num_samples = int(len(audio_chunk) * (native_rate / PIPER_RATE))
                            audio_chunk = scipy.signal.resample(audio_chunk, num_samples).astype(np.int16)
                        stream.write(audio_chunk.tobytes())
                    else:
                        self.current_volume = 0
                time.sleep(0.5) 
                    
        except Exception as e:
            print(f"Audio Error: {e}")
        finally:
            self.current_volume = 0 
            if self.current_audio_process:
                if self.current_audio_process.stdout: self.current_audio_process.stdout.close()
                if self.current_audio_process.poll() is None: self.current_audio_process.terminate()
                self.current_audio_process = None

    def _run_thinking_sound_loop(self):
        time.sleep(0.5)
        while self.thinking_sound_active.is_set():
            sound = self.get_random_sound(thinking_sounds_dir)
            if sound: self.play_sound(sound)
            for _ in range(50):
                if not self.thinking_sound_active.is_set(): return
                time.sleep(0.1)

    def get_random_sound(self, directory):
        if os.path.exists(directory):
            files = [f for f in os.listdir(directory) if f.endswith(".wav")]
            return os.path.join(directory, random.choice(files)) if files else None
        return None

    def play_sound(self, file_path):
        if not file_path or not os.path.exists(file_path): return
        try:
            with wave.open(file_path, 'rb') as wf:
                file_sr = wf.getframerate()
                data = wf.readframes(wf.getnframes())
                audio = np.frombuffer(data, dtype=np.int16)

            try:
                device_info = sd.query_devices(OUTPUT_DEVICE_NAME if OUTPUT_DEVICE_NAME is not None else sd.default.device[1])
                native_rate = int(device_info['default_samplerate'])
            except Exception:
                native_rate = 48000

            playback_rate = file_sr
            try:
                sd.check_output_settings(device=OUTPUT_DEVICE_NAME, samplerate=file_sr)
            except Exception:
                playback_rate = native_rate
                num_samples = int(len(audio) * (native_rate / file_sr))
                audio = scipy.signal.resample(audio, num_samples).astype(np.int16)

            sd.play(audio, playback_rate, device=OUTPUT_DEVICE_NAME)
            sd.wait() 
        except: pass

    def load_chat_history(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f: return json.load(f)
            except: pass
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    def save_chat_history(self):
        full = self.permanent_memory + self.session_memory
        conv = full[1:]
        if len(conv) > 10: conv = conv[-10:]
        with open(MEMORY_FILE, "w") as f: 
            json.dump([full[0]] + conv, f, indent=4)

if __name__ == "__main__":
    print("--- SYSTEM STARTING ---", flush=True)
    root = tk.Tk()
    app = BotGUI(root)
    root.mainloop()
