# 🤖 JARVIS — AI Terminal Assistant
### Version 6.0 | Local-First | Termux Edition

> **Built by [Green Bhai (Sabuj De)](https://www.youtube.com/@cirkimatrix)**
> A local-first, offline-capable AI terminal assistant engineered for Termux (Android CLI).
> Runs on your phone — no PC, no subscription, no cloud dependency.

---

## 📡 System Architecture

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│              COMMAND LAYER (Priority 0–3)            │
│  Identity • Time/Date • Tasks • Media • Battery etc. │
└──────────────────────────┬──────────────────────────┘
                           │ (no match → live pipeline)
                           ▼
┌─────────────────────────────────────────────────────┐
│                   CACHE CHECK                        │
│          knowledge.json (web-verified facts)         │
└──────────────────────────┬──────────────────────────┘
                           │ (cache miss)
                           ▼
┌─────────────────────────────────────────────────────┐
│              ORCHESTRATOR (Ollama LLM)               │
│   Decides route: WIKIPEDIA | WEB | LOCAL             │
└────┬──────────────────┬────────────────┬────────────┘
     │                  │                │
     ▼                  ▼                ▼
 Wikipedia          Web Scraper       Ollama LLM
 (DuckDuckGo)      (qwen2.5:0.5b)
     │                  │
     └──── fallback ─── ▼
                   Gemini 2.5 Flash
                  (Rate-Guarded API)
```

**Cascade Fallback Logic:**
- Wikipedia fails → Web → Local Ollama
- Web fails → Local Ollama
- Local Ollama fails → Gemini (rate-guarded)
- Gemini 429 → auto-wait + retry, OR serve raw web data

---

## ✨ Features

| Category | Capability |
|---|---|
| 🧠 **AI Engine** | Local Ollama LLM (`qwen2.5:0.5b`) — fully offline |
| ☁️ **Cloud Escalation** | Gemini 2.5 Flash — with rate guard (no 429 crashes) |
| 🌐 **Web Scraper** | DuckDuckGo Lite scraper (no API key needed) |
| 📖 **Wikipedia** | Direct encyclopedic lookup via `wikipedia` library |
| 📋 **Task Manager** | Persistent JSON to-do list (add / show / remove) |
| 🎵 **YouTube Stream** | `yt-dlp` + `mpv` background streaming |
| 🎶 **Local Music** | `.mp3` playback from Termux storage |
| 🔋 **Battery** | Live battery level via `termux-battery-status` (8s timeout) |
| 📍 **Location** | GPS coordinates via `termux-location` (15s timeout) |
| 🌤️ **Weather** | Real-time weather via Open-Meteo API |
| 🗣️ **TTS** | Voice output via `termux-tts-speak` (non-blocking) |
| 💾 **Knowledge Cache** | Auto-learns verified web facts to `knowledge.json` |
| 🛡️ **Rate Guard** | Prevents Gemini 429 — auto-spaces calls + countdown retry |
| 🤖 **Ollama Auto-Start** | Auto-launches `ollama serve` on startup — no manual tab |
| 🧠 **Signal 9 Guard** | RAM check, SIGTERM flush, `setsid` daemon detach |

---

## 📦 File Structure

```
Jarvis/
├── jarvis.py          # Main orchestrator — pipeline, fallback, I/O
├── commands.py        # All command handlers (tasks, media, battery, etc.)
├── core_functions.py  # Header, TTS, sound, display formatting
├── config.py          # All constants, API keys, file paths
├── check_deps.py      # Dependency preflight checker
├── setup.sh           # One-shot Termux installer script
├── requirements.txt   # Python dependencies
├── test_fixes.py      # Bug-fix verification suite (56 tests)
│
├── assets/            # Sound files
│   ├── startup.mp3
│   ├── shutdown.mp3
│   ├── response.mp3
│   └── error.mp3
│
├── conversations.json # Full conversation history (auto-created)
├── knowledge.json     # Web-verified fact cache (auto-created)
├── chat_log.json      # Session chat log (auto-created)
└── todo_list.json     # Task list (auto-created)
```

---

## 🚀 Installation (Termux — Android)

### Step 1 — Clone the project
```bash
pkg install git -y
git clone https://github.com/Sabuj3825/Jarvis
cd Jarvis
```

### Step 2 — Run the one-shot setup script
```bash
bash setup.sh
```

This automatically:
- Updates Termux packages
- Installs `python`, `mpv`, `termux-api`
- Grants storage permission (for local music)
- Installs all Python packages
- Asks for your Gemini API key (optional)
- Runs the dependency preflight check

### Step 3 — Install Ollama local LLM (optional but recommended)
```bash
pkg install ollama -y
ollama pull qwen2.5:0.5b
```
> Ollama auto-starts when you launch Jarvis. No separate tab needed.

### Step 4 — Set your Gemini API key (optional)
```bash
export GEMINI_API_KEY="your_key_here"
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.bashrc
```
Get a free key at: https://aistudio.google.com/

### Step 5 — Launch Jarvis
```bash
python jarvis.py
```

---

## 💬 Command Reference

```
┌─────────────────────────────────────────────────────────────────┐
│  📋 TASK TRACKING                                                │
│     add task [text]        → Add item to to-do list             │
│     show tasks             → Display all active tasks           │
│     remove task [number]   → Delete task by index number        │
│                                                                  │
│  🌐 BROWSER                                                      │
│     open google            → Open Google in mobile browser      │
│     open youtube           → Open YouTube in mobile browser     │
│                                                                  │
│  🎵 MEDIA                                                        │
│     play youtube [song]    → Stream from YouTube via yt-dlp     │
│     play music             → Play all .mp3 files in storage     │
│     play random music      → Play a random .mp3 track           │
│     list music             → Show all .mp3 files in storage     │
│     stop                   → Kill active media player           │
│                                                                  │
│  🔋 DEVICE METRICS                                               │
│     battery status         → Show battery level (8s timeout)    │
│     location               → Show GPS coordinates (15s timeout) │
│     weather                → Show temperature & wind speed      │
│                                                                  │
│  📅 TIME & DATE                                                  │
│     time                   → Current time                       │
│     date                   → Today's date                       │
│     calendar               → Current month calendar            │
│                                                                  │
│  🔎 FILE & CHAT MANAGEMENT                                       │
│     read file [path]       → Print file contents               │
│     read chat log          → Show last 4 conversation entries   │
│                                                                  │
│  🧠 RAG SEARCH                                                   │
│     search [query]         → Live DuckDuckGo web search         │
│     define [term]          → Wikipedia definition lookup        │
│                                                                  │
│  ⚙️ SYSTEM                                                       │
│     help                   → Show this command table            │
│     exit / quit            → Shutdown Jarvis cleanly            │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Live Pipeline Status Display

Every query shows its processing path in real-time:

```text
🧐 You > WHO IS THE CM OF WEST BENGAL

💾 [Cache Check]: Scanning knowledge base for known answer...
🔍 [Cache Miss]: No cached answer. Routing to live pipeline...
⚡ [Orchestrator]: Decision → WEB
🌐 [Web Scraper]: Searching live network data...
✅ [Web Scraper]: Live data captured.
📡 [Cloud Escalation]: Connecting to Gemini API matrix...
✅ [Cloud Escalation]: Gemini response received.

Jarvis [2026-07-01 22:15:42]: Mamata Banerjee is the Chief Minister of West Bengal.
```

**Example 2: Local AI & Cache Hit (Offline)**
```text
🧐 You > WHAT CAN YOU DO FOR ME

💾 [Cache Check]: Scanning knowledge base for known answer...
✅ [Cache Hit]: Serving answer from local knowledge matrix.
Jarvis [2026-07-01 21:25:12]: I'm glad I could help with that question! If you have a specific area in mind or something you'd like to discuss, feel free to share it. I'll do my best to provide the information and insights you're looking for. Let's get started!
```

---

## 🛡️ Rate Guard — No More 429 Errors

The Gemini Rate Guard prevents rate limit crashes **before they happen**:

```
# Normal use — calls auto-spaced:
⏳ [Rate Guard]: Spacing call by 2.1s to stay under rate limit...

# Near limit (14 calls in 60s) — auto-countdown:
⏳ [Rate Guard]: 14 req/min limit reached. Waiting 23s...
   ⏱  23s remaining...

# Rare 429 slip-through — auto-retry:
⚠️  [Rate Guard]: Got 429. Auto-retrying in 62s...
✅ [Rate Guard]: Retry succeeded.
```

**Limits respected:**
- Free tier: 15 req/min — Guard uses max 14 (safety margin)
- Minimum gap: 4.3 seconds between consecutive calls

---

## 🧠 Fallback Cascade System

When any pipeline component fails, Jarvis **never crashes** — it falls through:

```
Wikipedia ──FAIL──► Web Scraper ──FAIL──► Ollama LLM
                        │
                      SUCCESS
                        │
                        ▼
                  Gemini 2.5 Flash ──429──► Raw Web Data (shown directly)
                        │
                      SUCCESS
                        │
                        ▼
                  Final Answer ──► Jarvis prints response
```

---

## ⚙️ Configuration (`config.py`)

| Variable | Purpose | Default |
|---|---|---|
| `DEVELOPER_NAME` | Your name shown in responses | `Sabuj De` |
| `DEVELOPER_ALIAS` | Alias / brand name | `Green Bhai` |
| `LOCAL_MODEL` | Ollama model to use | `qwen2.5:0.5b` |
| `OLLAMA_URL` | Ollama API endpoint | `http://127.0.0.1:11434/api/chat` |
| `MAX_CHAT_HISTORY` | Context window depth | `6` messages |
| `API_KEY` | Gemini API key (env var) | `GEMINI_API_KEY` |
| `MUSIC_DIR` | Path to music folder | Termux storage music |

---

## 🔧 Dependency Check

Run at any time to check system health:
```bash
python check_deps.py
```

Output example:
```
[SECTION 4: LOCAL PORTS & CLOUD MATRIX SUITE]
✓ PASSED: Ollama Core Daemon running
✓ PASSED: Web crawler returned live text stream blocks
✓ PASSED: Gemini Matrix Link — API responding
```

---

## 🧪 Test Suite

Verify all 56 bug fixes are intact:
```bash
python test_fixes.py
```

Expected output:
```
✓ Passed : 56
✗ Failed : 0
⊘ Skipped: 0 (Termux-only hardware)
🚀 ALL FIXES VERIFIED — SYSTEM READY FOR TERMUX DEPLOYMENT
```

---

## 🔗 Developer Links

| Platform | Link |
|---|---|
| 🎥 YouTube | [youtube.com/@cirkimatrix](https://www.youtube.com/@cirkimatrix) |
| 💻 GitHub | [github.com/Sabuj3825](https://github.com/Sabuj3825) |
| 📢 Telegram | [t.me/GreenBhaiOfficial](https://t.me/GreenBhaiOfficial) |

---

## 📜 License

Built with ❤️ by **Green Bhai (Sabuj De)** for the Termux community.
Free to use, modify, and share.
