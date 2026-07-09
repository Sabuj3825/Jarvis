import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- DEVELOPER BRANDING OVERRIDES ---
DEVELOPER_NAME = "Sabuj De"
DEVELOPER_ALIAS = "Green Bhai"
YOUTUBE_CHANNEL = "https://www.youtube.com/@cirkimatrix"
GITHUB_PROFILE = "https://github.com/Sabuj3825"
TELEGRAM_CHANNEL = "https://t.me/GreenBhaiOfficial"

# --- PERSISTENT DUAL-LAYER STORAGE BASES ---
CONVERSATIONS_FILE = os.path.join(_BASE_DIR, "conversations.json")
KNOWLEDGE_FILE     = os.path.join(_BASE_DIR, "knowledge.json")
TODO_FILE          = os.path.join(_BASE_DIR, "todo_list.json")
LOG_FILE           = os.path.join(_BASE_DIR, "chat_log.json")

# --- HARDWARE & LOCAL TUNING PROPERTIES ---
LOCAL_MODEL = "qwen2.5:0.5b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MAX_CHAT_HISTORY = 6  # Context slider depth boundary
CACHE_TTL_DAYS  = 30   # Web-verified facts expire after 30 days

# --- CLOUD ESCALATION PARAMETERS ---
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
HEADERS = {"Content-Type": "application/json"}

# --- OPENROUTER INTEGRATION ---
# Set OPENROUTER_API_KEY env var to enable OpenRouter cloud fallback.
# Run update_openrouter_models.py once to populate openrouter_models.json.
OPENROUTER_API_KEY     = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODELS_FILE = os.path.join(_BASE_DIR, "openrouter_models.json")
OPENROUTER_ENABLED     = bool(OPENROUTER_API_KEY)   # auto-detected

# --- SYSTEM AUTOMATION PATHS ---
MUSIC_DIR = "/data/data/com.termux/files/home/storage/music"
GOOGLE_SEARCH_URL = "https://www.google.com/search"
WEB_USER_AGENT = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; Samsung Galaxy S22) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"}

# --- NOTIFICATION AUDIO SOUND SCHEMES ---
STARTUP_SOUND_FILE = "assets/startup.mp3"
SHUTDOWN_SOUND_FILE = "assets/shutdown.mp3"
RESPONSE_SOUND_FILE = "assets/response.mp3"
ERROR_SOUND_FILE = "assets/error.mp3"

# --- GLOBAL COMMAND CONSTANTS ---
CMD_EXIT = "exit"
CMD_QUIT = ["quit", "shutdown", "power off"]
CMD_TIME = "time"
CMD_DATE = "date"
CMD_CALENDAR = "calendar"
CMD_BATTERY = ["battery", "battery status", "charge"]
CMD_LOCATION = "location"
CMD_WEATHER = ["weather", "temperature", "forecast"]
CMD_ADD_TASK = "add task "
CMD_SHOW_TASKS = "show tasks"
CMD_REMOVE_TASK = "remove task "
CMD_READ_FILE = "read file "

chat_log = []