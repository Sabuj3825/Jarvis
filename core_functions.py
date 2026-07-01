import os
import re
import subprocess
from colorama import Fore, Style
import config

current_music_process = None

def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print(Fore.CYAN + Style.BRIGHT + "🤖 JARVIS AI | Termux Executive Mainframe")
    print(Fore.WHITE + Style.BRIGHT + "# ==================================================== #")
    print(Fore.LIGHTGREEN_EX + f"  👉 Core System Architecture Developed by: {config.DEVELOPER_ALIAS}")
    print(Fore.LIGHTGREEN_EX + f"  👉 Build Release Protocol Matrix: Version 6.0 [Local-First]")
    print(Fore.WHITE + Style.BRIGHT + "# ==================================================== #\n")
    
    print(Fore.MAGENTA + Style.BRIGHT + "📊 ACTIVE PROTOCOLS MANIFEST:")
    print(Fore.WHITE + Style.BRIGHT + "+-----------------------+----------------------------------+")
    print(Fore.CYAN + "| CORE PIPELINE         " + Fore.CYAN + "| SYSTEM FUNCTION CAPABILITY       |")
    print(Fore.WHITE + Style.BRIGHT + "+-----------------------+----------------------------------+")
    print(Fore.YELLOW + "| ⚙️  Setup Wizard      " + Fore.WHITE + "| First-time user profile parsing  |")
    print(Fore.YELLOW + "| 🧠 Long-Term Memory   " + Fore.WHITE + "| Persistent local vector matrices |")
    print(Fore.YELLOW + "| 🎵 Media Stream Node  " + Fore.WHITE + "| Background yt-dlp & mpv hookouts |")
    print(Fore.YELLOW + "| 📡 Live Scrapers      " + Fore.WHITE + "| Dynamic Google & Wikipedia crawls|")
    print(Fore.YELLOW + "| 🔋 Telemetry Tracker  " + Fore.WHITE + "| Termux battery, weather, loc apps|")
    print(Fore.YELLOW + "| 📋 Task Manager       " + Fore.WHITE + "| Persistent JSON to-do matrices   |")
    print(Fore.YELLOW + "| 🛡️  Identity Shield   " + Fore.WHITE + "| Solid custom branding overrides  |")
    print(Fore.YELLOW + "| ⚡ Local-First Core   " + Fore.WHITE + "| Ollama routing with Cloud Escal. |")
    print(Fore.WHITE + Style.BRIGHT + "+-----------------------+----------------------------------+")
    print(Style.RESET_ALL)

def speak(text):
    """Non-blocking TTS — runs in background so prompt appears immediately."""
    try:
        clean_text = re.sub(r"```[\s\S]*?```", '[Code block printed to terminal]', text)
        clean_text = clean_text.replace("**", "").replace("__", "").replace("#", "")
        clean_text = " ".join(clean_text.split())
        # Popen = non-blocking: TTS speaks in background, main loop continues instantly
        subprocess.Popen(
            ['termux-tts-speak', clean_text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def play_sound(file_name):
    """Non-blocking sound — runs in background so prompt appears immediately."""
    if not os.path.exists(file_name):
        return
    try:
        # Popen = non-blocking: sound plays in background, main loop continues instantly
        subprocess.Popen(
            ['mpv', '--really-quiet', file_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def stop_music_playback():
    global current_music_process
    if current_music_process and current_music_process.poll() is None:
        try:
            current_music_process.terminate()
            current_music_process.wait(timeout=1)
            current_music_process = None
            return "⏹️ Playback stopped natively."
        except Exception as e:
            play_sound(config.ERROR_SOUND_FILE)
            return f"❌ Error stopping music: {e}"
    return "⏹️ No music is currently playing."

def display_message(role, text, timestamp):
    if role == "user":
        color = Fore.YELLOW
        tag = "You"
    elif role == "jarvis":
        color = Fore.LIGHTGREEN_EX
        tag = "Jarvis"
    else:
        color = Fore.CYAN
        tag = "System"
    print(f"{color}{tag} [{timestamp}]: {text}\n")