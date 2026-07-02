import os
import json
import requests
import datetime
import calendar
import wikipedia
import subprocess
import glob
import random
import re
from colorama import Fore, Style
import config
import core_functions

# --- CONVERSATIONAL WORDS & PHRASES — always LOCAL, never Wikipedia/Web ---
CONVERSATIONAL_TOKENS = {
    'ok', 'okay', 'yes', 'no', 'nope', 'yep', 'sure', 'thanks',
    'thank', 'bye', 'goodbye', 'hello', 'hi', 'hey', 'alright',
    'great', 'good', 'nice', 'cool', 'fine', 'got it', 'understood',
    'please', 'sorry', 'hmm', 'hm', 'right', 'indeed', 'exactly'
}
CONVERSATIONAL_PHRASES = [
    'u are', 'you are', 'wrong ans', 'wrong answer', 'incorrect', 'now this is correct',
    'this is correct', 'that is wrong', 'not right', 'you gave wrong', 'giving wrong'
]

# --- NEW DECISION ENGINE ---
def get_tool_routing_decision(user_query):
    """Asks the local model to categorize the query for efficient routing."""
    # SHORT-CIRCUIT: Single conversational words → always LOCAL (Bugs B & C fix)
    stripped = user_query.lower().strip().strip("'\".,!?")
    if stripped in CONVERSATIONAL_TOKENS or len(stripped.split()) <= 1 and len(stripped) <= 4:
        return 'local'

    prompt = (
        "Categorize this user query into exactly ONE word only — no explanation: "
        "'web' (needs live data, current events, news, real people's current roles), "
        "'wikipedia' (needs static encyclopedic knowledge, history, science concepts), "
        "'local' (greeting, math, file task, system command, identity check, chit-chat). "
        f"Query: {user_query}"
    )
    try:
        res = requests.post(config.OLLAMA_URL, json={
            "model": config.LOCAL_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.0}  # Deterministic routing
        }, timeout=5)
        raw = res.json()["message"]["content"].lower().strip()
        # Extract the first recognized category keyword — fixes tiny model verbosity
        for keyword in ['wikipedia', 'web', 'local']:
            if keyword in raw:
                return keyword
        return 'web'  # Default fallback if no keyword matched
    except Exception:
        return 'web'  # Default fallback

def load_tasks():
    if os.path.exists(config.TODO_FILE):
        with open(config.TODO_FILE, "r") as f:
            try: return json.load(f)
            except Exception: return []
    return []

def save_tasks(tasks):
    with open(config.TODO_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

def search_google_scrape(query):
    """
    Uses DuckDuckGo Lite HTML endpoint to bypass aggressive Google anti-bot blocks.
    Perfectly tailored for headless Termux environments.
    """
    try:
        url = "https://lite.duckduckgo.com/lite/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        res = requests.post(url, data={"q": query}, headers=headers, timeout=8)
        res.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')
        
        snippets = [td.text.strip() for td in soup.find_all('td', class_='result-snippet')]
        
        if snippets:
            return " ".join(snippets[:2])
    except Exception as e:
        pass
    
    return None

def handle_command(cmd, chat_log):
    cmd = cmd.lower().strip()
    now = datetime.datetime.now()

    # =========================================================================
    # PRIORITY 0: INSTANT AUDIO CONTROLS
    # =========================================================================
    if cmd in ["stop", "stop music", "stop song", "stop youtube", "stop muisic"]:
        return core_functions.stop_music_playback()

    # =========================================================================
    # PRIORITY 1: HARDCODED IDENTITY PIPELINES
    # =========================================================================
    assignment_phrases = ["your name is", "call you", "i made you", "sabuj made you", "i am your boss", "sabuj is your boss", "my name is"]
    if any(phrase in cmd for phrase in assignment_phrases):
        return None

    if any(x in cmd for x in ["who are you", "who u", "who you", "your name", "wht is your name", "whz is your name"]):
        return "🤖 I am Jarvis. From executing local shell commands to scraping dynamic networks, I am here to make your computer tasks smooth and efficient."

    if any(x in cmd for x in ["tell me about yourself", "tell me about u", "tell me about you", "tell me about your self"]):
        return f"🤖 I am Jarvis, a custom personal terminal assistant created by {config.DEVELOPER_ALIAS} to streamline your Unix workflows, access automation layers, and handle local-first processing task tracks."

    if any(x in cmd for x in ["who made you", "who build u", "who built you", "who build you", "who created you", "who is your creator", "creator of you", "developer", "devoloper", "develop you", "devolop you", "made you"]):
        return (
            f"🧠 [System Origin]: I was developed and brought to life by **{config.DEVELOPER_NAME}** (popularly known as **{config.DEVELOPER_ALIAS}**).\n\n"
            f"🚀 Check out his development pipelines here:\n"
            f"🎥 YouTube Channel: {config.YOUTUBE_CHANNEL}\n"
            f"💻 GitHub: {config.GITHUB_PROFILE}\n"
            f"📢 Telegram: {config.TELEGRAM_CHANNEL}"
        )

    if any(x in cmd for x in ["who is your boss", "who is your master", "who do you work for"]):
        return "🧠 [Local Brain Memory]: My absolute system loyalty belongs to my master, Sabuj (Green Bhai)."

    if any(x in cmd for x in ["my name", "what is my name", "who am i", "wht is my name"]):
        return f"🧠 [Local Brain Memory]: Your name is {config.DEVELOPER_NAME} ({config.DEVELOPER_ALIAS})."

    # =========================================================================
    # PRIORITY 1.5: CASUAL CONVERSATIONAL GATES
    # =========================================================================
    if cmd in ["hi", "hello", "hey", "greetings", "yo"]:
        return "👋 Hello! How can I assist you with your terminal today?"

    if cmd in ["how are you", "how are you?", "how are you doing", "whats up", "what's up"]:
        return "🤖 All systems are running at maximum efficiency. How can I help you, boss?"

    if cmd in ["good morning", "good afternoon", "good evening", "goodnight", "good night"]:
        return f"👋 {cmd.capitalize()}! Let me know if you need any tasks executed."

    if cmd in ["thank you", "thanks", "good job", "awesome", "nice"]:
        return "✅ You're very welcome. Ready for the next command."

    # =========================================================================
    # PRIORITY 2: SHELL INTERACTION PATHWAYS & UTILITIES
    # =========================================================================
    if cmd in ["clear", "cls", "clear screen"]:
        os.system('cls' if os.name == 'nt' else 'clear')
        return "🧹 Terminal surface wiped clean."

    if "read chat" in cmd or "read log" in cmd or "reade chat log" in cmd:
        if os.path.exists(config.LOG_FILE):
            with open(config.LOG_FILE, "r") as f:
                try:
                    logs = json.load(f)
                    summary = ""
                    for entry in logs[-4:]:
                        summary += f"🕒 [{entry.get('timestamp', '')}] {entry['role'].upper()}: {entry['text']}\n"
                    return f"📋 Here are your latest local interaction logs:\n\n{summary}"
                except Exception:
                    return "❌ Local log indexing matrix is currently busy or corrupted."
        return "❌ Active conversation logs missing on local storage blocks."

    if cmd.startswith(config.CMD_ADD_TASK):
        task = cmd.replace(config.CMD_ADD_TASK, "", 1).strip()
        if task:
            tasks = load_tasks()
            tasks.append(task)
            save_tasks(tasks)
            return f"✅ Task logged: {task}"
        return "⚠️ Specify a clean string value to append to your to-do matrices."

    if "show task" in cmd:  # matches both 'show task' and 'show tasks'
        tasks = load_tasks()
        if not tasks: return "📫 Your to-do list file matrix is completely empty."
        result = "📋 Active To-Do Entries:\n"
        for i, t in enumerate(tasks, 1): result += f"{i}. {t}\n"
        return result.strip()

    if cmd.startswith(config.CMD_REMOVE_TASK):
        try:
            num = int(cmd.split()[-1]) - 1
            tasks = load_tasks()
            if 0 <= num < len(tasks):
                removed = tasks.pop(num)
                save_tasks(tasks)
                return f"🗑️ Purged task entry: {removed}"
            return "❌ Target task index is outside array bounds."
        except Exception:
            return "⚠️ Core syntax mismatch. Usage: remove task [number]"

    if "open youtube" in cmd:
        subprocess.run(["termux-open", "https://m.youtube.com"])
        return "▶️ Opening mobile YouTube interface..."

    if "open google" in cmd:
        subprocess.run(["termux-open", "https://google.com"])
        return "🌐 Launching search gateway..."

    if "youtube video" in cmd or "youtube music" in cmd or "youtube muisic" in cmd or cmd.startswith("play youtube"):
        query = cmd.replace("play youtube video", "").replace("play youtube music", "").replace("play youtube muisic", "").replace("play youtube", "").strip()
        if not query: return "⚠️ Core script needs a query parameter: play youtube [track name]"
        try:
            print(Fore.CYAN + "📡 Hooking network interfaces to stream via yt-dlp...")
            res = subprocess.run(["yt-dlp", "--format", "best[ext=mp4]/best", "-g", f"ytsearch1:{query}"], capture_output=True, text=True)
            if res.returncode != 0 or not res.stdout.strip():
                subprocess.run(["termux-open-url", f"https://www.youtube.com/results?search_query={query}"])
                return "⚠️ Stream link aggregation failed. Shifting to standard browser routing."
            
            v_url = res.stdout.strip().split("\n")[0]
            core_functions.stop_music_playback()
            core_functions.current_music_process = subprocess.Popen(['mpv', v_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"▶️ Streaming background media link: {query}"
        except Exception as e:
            return f"❌ Package driver failure: {e}."

    if re.search(r'\b' + config.CMD_TIME + r'\b', cmd):
        return "🕒 " + now.strftime("%I:%M %p")

    # GUARD: Skip if 'date' is used as a VERB (social/relationship context), not the calendar date
    DATE_VERB_PATTERNS = ['to date', 'date a ', 'date an ', 'date someone', 'date her',
                          'date him', 'date them', 'date girl', 'date boy', 'dating',
                          'how date', 'date people', 'first date', 'date night', 'date with']
    _is_verb_date = any(p in cmd for p in DATE_VERB_PATTERNS)
    if re.search(r'\b' + config.CMD_DATE + r'\b', cmd) and not _is_verb_date:
        return "📅 " + now.strftime("%A, %B %d, %Y")

    if config.CMD_CALENDAR in cmd:
        return calendar.month(now.year, now.month)

    if any(kw in cmd for kw in config.CMD_BATTERY):
        try:
            res = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=8)
            return "🔋 Battery Telemetry Status:\n" + (res.stdout or "⚠️ No data returned from battery API.")
        except subprocess.TimeoutExpired:
            return "⚠️ [Battery]: termux-battery-status timed out (>8s). Is Termux:API installed?"
        except Exception as e:
            return f"❌ [Battery]: Failed — {str(e)[:60]}"

    if config.CMD_LOCATION in cmd:
        try:
            print(Fore.CYAN + "📍 [Location]: Acquiring GPS fix (up to 15s)...")
            res = subprocess.run(["termux-location"], capture_output=True, text=True, timeout=15)
            return "📍 Location Frame Matrices:\n" + (res.stdout or "⚠️ No GPS data returned.")
        except subprocess.TimeoutExpired:
            return "⚠️ [Location]: GPS timed out (>15s). Enable location & Termux:API."
        except Exception as e:
            return f"❌ [Location]: Failed — {str(e)[:60]}"

    if any(kw in cmd for kw in config.CMD_WEATHER):
        try:
            print(Fore.CYAN + "🌤️ [Weather]: Acquiring GPS fix for location (up to 15s)...")
            loc_res = subprocess.run(["termux-location"], capture_output=True, text=True, timeout=15)
            loc = json.loads(loc_res.stdout)
            print(Fore.CYAN + "📡 [Weather]: Fetching live weather data...")
            w_url = f"https://api.open-meteo.com/v1/forecast?latitude={loc['latitude']}&longitude={loc['longitude']}&current_weather=true"
            w_data = requests.get(w_url, timeout=10).json()['current_weather']
            return f"🌤️ Coordinate Report: {w_data['temperature']}\u00b0C, Winds at {w_data['windspeed']} km/h"
        except subprocess.TimeoutExpired:
            return "⚠️ [Weather]: GPS timed out (>15s). Enable location & Termux:API."
        except requests.exceptions.Timeout:
            return "⚠️ [Weather]: Weather API timed out (>10s). Check internet connection."
        except Exception as e:
            return f"❌ [Weather]: Failed — {str(e)[:60]}"

    if cmd.startswith(config.CMD_READ_FILE):
        f_name = cmd.replace(config.CMD_READ_FILE, "", 1).strip()
        if os.path.exists(f_name):
            with open(f_name, "r") as f: return f.read()
        return "❌ Targeted asset file path could not be found."

    if "music" in cmd or "song" in cmd or "muisic" in cmd:
        if "list" in cmd:
            if not os.path.exists(config.MUSIC_DIR): return "🎶 Audio index folder empty."
            tracks = glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3"))
            if not tracks: return "🎶 Audio files missing."
            return "🎶 Track Array:\n" + "\n".join([f"{i}. {os.path.basename(t)}" for i, t in enumerate(tracks, 1)])
        else:
            if not os.path.exists(config.MUSIC_DIR): return "❌ Targeted music registry is empty."
            tracks = glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3"))
            if not tracks: return "❌ Storage contains no playable .mp3 layers."
            
            if "random" in cmd or cmd.strip() in ["play music", "play muisic", "play random music", "play random muisic"]:
                chosen = random.choice(tracks)
                core_functions.stop_music_playback()
                core_functions.current_music_process = subprocess.Popen(['mpv', '--no-video', chosen], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"🎶 Playing random jukebox track: {os.path.basename(chosen)}"
                
            search = cmd.replace("play song", "").replace("play music", "").replace("play muisic", "").strip()
            for t in tracks:
                if search in os.path.basename(t).lower():
                    core_functions.stop_music_playback()
                    core_functions.current_music_process = subprocess.Popen(['mpv', '--no-video', t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"🎶 Playing: {os.path.basename(t)}"
            return "❌ Track query key failed to find any matching files on local disk."

    # =========================================================================
    # PRIORITY 3: SYSTEM INTERACTIVE CAPABILITY MAPS
    # =========================================================================
    # GUARD: Only show help table for CLEAR INTENT — not for 'can you help me with X' or 'what is your capability'
    # Rule: 'help' must be standalone OR 'show help'/'get help' — NOT mid-sentence like 'help me understand'
    # Rule: 'capability/features' alone triggers table — but 'what is your capability' should go to Ollama
    _HELP_EXACT = ['help', 'show commands', 'commands', 'show help', 'get help', 'what can you do', 'what do you do']
    _HELP_BLOCKED = ['help me', 'can you help', 'please help', 'help with', 'help understand',
                     'how can you help', 'how do you help', 'what is your capability',
                     'what are your capability', 'whats your capability', 'wht is your capability',
                     'what is your feature', 'your capability', 'your features']
    _is_help_blocked = any(b in cmd for b in _HELP_BLOCKED)
    _is_help_intent = any(cmd == e or cmd.startswith(e) for e in _HELP_EXACT)
    if _is_help_intent and not _is_help_blocked:
        return (
            f"{Fore.MAGENTA}{Style.BRIGHT}\n📊 JARVIS PIPELINE PROTOCOL DIRECTORY:\n"
            f"{Fore.WHITE}{Style.BRIGHT}+-----------------------+-----------------------------------------------------+\n"
            f"{Fore.CYAN}| CONTROL SUITE         | COMMAND REGISTRY INTERFACES                         |\n"
            f"{Fore.WHITE}{Style.BRIGHT}+-----------------------+-----------------------------------------------------+\n"
            f"{Fore.YELLOW}| 📋 Task Tracking       {Fore.WHITE}| add task [text] | show tasks | remove task [num]    |\n"
            f"{Fore.YELLOW}| 🌐 Global Browser     {Fore.WHITE}| open google | open youtube                          |\n"
            f"{Fore.YELLOW}| 🎵 Cloud Streamer     {Fore.WHITE}| play youtube [song name] | stop                     |\n"
            f"{Fore.YELLOW}| 🎶 Local Media player {Fore.WHITE}| play music | play random music | list music        |\n"
            f"{Fore.YELLOW}| 🔋 Device Metrics     {Fore.WHITE}| battery status | location | weather                 |\n"
            f"{Fore.YELLOW}| 📅 Base Telemetry     {Fore.WHITE}| time | date | calendar                              |\n"
            f"{Fore.YELLOW}| 🔎 File Management    {Fore.WHITE}| read file [file_path] | read chat log               |\n"
            f"{Fore.YELLOW}| 🧠 RAG Neural Matrix  {Fore.WHITE}| search [query] | define [term]                      |\n"
            f"{Fore.WHITE}{Style.BRIGHT}+-----------------------+-----------------------------------------------------+\n"
            f"{Fore.LIGHTBLUE_EX}💡 Master Tip: Input 'stop' at any console prompt line to kill active background players.\n"
        )

    # =========================================================================
    # PRIORITY 4: SEARCH & DEFINE HANDLERS (RAG Neural Matrix — Bug 13 fix)
    # =========================================================================
    if cmd.startswith("search ") or cmd == "search":
        query = cmd.replace("search", "", 1).strip()
        if query:
            result = search_google_scrape(query)
            return f"🔎 Search Result:\n{result}" if result else "❌ No live results found for that query."
        return "⚠️ Usage: search [your query]"

    if cmd.startswith("define ") or cmd == "define":
        term = cmd.replace("define", "", 1).strip()
        if term:
            try:
                return wikipedia.summary(term, sentences=2, auto_suggest=True)
            except Exception:
                return f"❌ Could not find a definition for '{term}'."
        return "⚠️ Usage: define [term]"

    # =========================================================================
    # PRIORITY 5: KNOWLEDGE BASE MANAGEMENT
    # =========================================================================
    if cmd.startswith("forget "):
        key_to_forget = cmd.replace("forget ", "", 1).strip()
        kb = {}
        if os.path.exists(config.KNOWLEDGE_FILE):
            with open(config.KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                try: kb = json.load(f)
                except Exception: pass
        
        if key_to_forget in kb:
            del kb[key_to_forget]
            with open(config.KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
                json.dump(kb, f, indent=2)
            return f"🗑️ Forgotten cached fact for: '{key_to_forget}'"
        return f"⚠️ No cached fact found for '{key_to_forget}'."

    return None