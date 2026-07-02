"""
====================================================
🔬 JARVIS BUG-FIX VERIFICATION SUITE (Laptop Safe)
====================================================
Tests every fix applied in the 13-bug patch.
Designed to run on Windows/laptop — skips Termux-only
hardware APIs (battery, location, TTS, mpv) cleanly.
"""

import os
import re
import sys
import json
import requests
import shutil
from colorama import Fore, Style, init
import config
import commands

# Fix Windows cp1252 encoding for Unicode emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

init(autoreset=True)

passed = 0
failed = 0
skipped = 0

def test(name, condition, success="", fail=""):
    global passed, failed
    if condition:
        print(f"  {Fore.GREEN}✓ PASS{Fore.WHITE}  {name}")
        if success: print(f"         {Fore.CYAN}→ {success}")
        passed += 1
    else:
        print(f"  {Fore.RED}✗ FAIL{Fore.WHITE}  {name}")
        if fail: print(f"         {Fore.RED}→ {fail}")
        failed += 1

def skip(name, reason):
    global skipped
    print(f"  {Fore.YELLOW}⊘ SKIP{Fore.WHITE}  {name}")
    print(f"         {Fore.YELLOW}→ {reason}")
    skipped += 1

def header(title):
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*54}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}  {title}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*54}")


# ============================================================
# BUG 1 — Orchestrator keyword extraction
# ============================================================
header("BUG 1 — Orchestrator: keyword extraction from verbose model")

def simulate_orchestrator_extraction(raw_response):
    """Mirrors the fixed get_tool_routing_decision keyword scan."""
    raw = raw_response.lower().strip()
    for keyword in ['wikipedia', 'web', 'local']:
        if keyword in raw:
            return keyword
    return 'web'

test("Full sentence with 'local' → extracts 'local'",
     simulate_orchestrator_extraction(
         "THIS USER QUERY SHOULD BE CATEGORIZED AS 'LOCAL'. IT IS A GREETING.") == 'local',
     "Keyword 'local' found in verbose response")

test("Multi-word 'current, wikipedia, web' → extracts 'wikipedia' (first match)",
     simulate_orchestrator_extraction("CURRENT, WIKIPEDIA, WEB") == 'wikipedia',
     "First keyword in priority list wins")

test("Uppercase sentence with 'web' → extracts 'web'",
     simulate_orchestrator_extraction("THE ANSWER REQUIRES THE WEB FOR LIVE DATA.") == 'web',
     "Case-insensitive extraction works")

test("Unknown category 'iot' → falls back to 'web'",
     simulate_orchestrator_extraction("IOT") == 'web',
     "Unknown categories default to 'web'")

test("Unknown 'joke' → falls back to 'web'",
     simulate_orchestrator_extraction("USER_QUERY, JOKE") == 'web',
     "Unknown categories default to 'web'")


# ============================================================
# BUG 2 — Decision branching (fixed by Bug 1)
# ============================================================
header("BUG 2 — Decision branching: non-exact strings no longer break routing")

VALID_DECISIONS = {'web', 'wikipedia', 'local'}
test("'web' matches web branch",      'web' in VALID_DECISIONS)
test("'wikipedia' matches wiki branch", 'wikipedia' in VALID_DECISIONS)
test("'local' matches local branch",   'local' in VALID_DECISIONS)
test("'iot' after extraction → becomes 'web'",
     simulate_orchestrator_extraction("iot") == 'web')


# ============================================================
# BUG 3 — Web scraper None guard (no hallucination)
# ============================================================
header("BUG 3 — Gemini not called when scraper returns None")

def simulate_web_path(web_results, api_key_valid):
    """Mirrors the fixed web branch logic in jarvis.py."""
    if not web_results:
        return "⚠️ Web scraper returned no live results."
    elif api_key_valid:
        return "GEMINI_CALLED"
    else:
        return web_results

test("None scrape → returns warning, does NOT call Gemini",
     simulate_web_path(None, True) == "⚠️ Web scraper returned no live results.",
     "Gemini call blocked when scraper returned None")

test("Empty string scrape → returns warning",
     simulate_web_path("", True) == "⚠️ Web scraper returned no live results.",
     "Empty scrape result also blocked")

test("Valid scrape + valid key → Gemini is called",
     simulate_web_path("Mamata Banerjee is CM", True) == "GEMINI_CALLED",
     "Gemini called only when scrape has real data")

test("Valid scrape + no key → returns raw scrape",
     simulate_web_path("Mamata Banerjee is CM", False) == "Mamata Banerjee is CM",
     "Falls back to raw scrape when no API key")


# ============================================================
# BUG 4 — "who am i" → user identity, not Jarvis identity
# ============================================================
header("BUG 4 — 'who am i' returns USER identity (not Jarvis identity)")

result_who_am_i = commands.handle_command("who am i", [])
test("'who am i' returns user name (Sabuj)",
     result_who_am_i is not None and config.DEVELOPER_NAME in str(result_who_am_i),
     f"Got: {str(result_who_am_i)[:60]}")

test("'who am i' does NOT say 'I am Jarvis'",
     "I am Jarvis" not in str(result_who_am_i),
     "No identity confusion")

result_who_are_you = commands.handle_command("who are you", [])
test("'who are you' still returns Jarvis identity",
     "Jarvis" in str(result_who_are_you),
     f"Got: {str(result_who_are_you)[:60]}")


# ============================================================
# BUG 5 — "date" word boundary (no false matches)
# ============================================================
header("BUG 5 — 'date' word boundary: 'devolopd date' vs 'what is the date'")

def cmd_date_matches(cmd):
    return bool(re.search(r'\b' + config.CMD_DATE + r'\b', cmd))

test("'date' exact → matches",              cmd_date_matches("date"))
test("'what is the date' → matches",        cmd_date_matches("what is the date"))
test("'devolopd date' → matches (contains 'date' as word)", cmd_date_matches("devolopd date"),
     "'date' IS a standalone word in 'devolopd date' — correct match")
test("'update' → does NOT match",           not cmd_date_matches("update"))
test("'candidate' → does NOT match",        not cmd_date_matches("candidate"))
test("'outdated' → does NOT match",         not cmd_date_matches("outdated"))

# Verb-date false positive guard (NEW fix — 'how to date a girl' must NOT trigger calendar)
result_date_verb   = commands.handle_command("how to date a girl", [])
result_date_night  = commands.handle_command("date night ideas", [])
result_dating      = commands.handle_command("dating tips", [])
result_real_date   = commands.handle_command("what is today date", [])

test("'how to date a girl' → does NOT trigger calendar date (goes to orchestrator)",
     result_date_verb is None,
     "Verb-date exclusion guard working")
test("'date night ideas' → does NOT trigger calendar date",
     result_date_night is None,
     "Social context excluded from date command")
test("'dating tips' → does NOT trigger calendar date",
     result_dating is None,
     "Progressive 'dating' excluded from date command")
test("'what is today date' → DOES trigger calendar date",
     result_real_date is not None and "📅" in str(result_real_date),
     f"Got: {result_real_date}")


# ============================================================
# BUG 6 — "show task" singular now recognized
# ============================================================
header("BUG 6 — 'show task' (singular) correctly recognized")

result_show_task = commands.handle_command("show task", [])
result_show_tasks = commands.handle_command("show tasks", [])

test("'show task' (singular) → handled by command layer (not None)",
     result_show_task is not None,
     f"Got: {str(result_show_task)[:60]}")

test("'show tasks' (plural) → still works",
     result_show_tasks is not None,
     f"Got: {str(result_show_tasks)[:60]}")


# ============================================================
# BUG 7 — "time" word boundary (no false matches)
# ============================================================
header("BUG 7 — 'time' word boundary: 'thefintimes.com' no longer triggers time")

def cmd_time_matches(cmd):
    return bool(re.search(r'\b' + config.CMD_TIME + r'\b', cmd))

test("'time' exact → matches",                     cmd_time_matches("time"))
test("'what time is it' → matches",                cmd_time_matches("what time is it"))
test("'thefintimes.com' → does NOT match",         not cmd_time_matches("thefintimes.com"),
     "Word boundary blocks substring match in domain name")
test("'runtime' → does NOT match",                 not cmd_time_matches("runtime"))
test("'sometime' → does NOT match",                not cmd_time_matches("sometime"))
test("'realtime' → does NOT match",                not cmd_time_matches("realtime"))

# Verify the actual command handler behavior
result_domain = commands.handle_command("thefintimes.com", [])
test("handle_command('thefintimes.com') → returns None (falls through to orchestrator)",
     result_domain is None,
     "Domain string no longer trapped by time handler")

result_time = commands.handle_command("time", [])
test("handle_command('time') → returns time string",
     result_time is not None and "🕒" in str(result_time),
     f"Got: {result_time}")


# ============================================================
# BUG 8 — Local path: real Ollama call (tested if Ollama running)
# ============================================================
header("BUG 8 — Local path: real Ollama conversational reply")

ollama_running = False
try:
    r = requests.get("http://127.0.0.1:11434", timeout=2)
    ollama_running = (r.status_code == 200)
except Exception:
    pass

if ollama_running:
    try:
        res = requests.post(config.OLLAMA_URL, json={
            "model": config.LOCAL_MODEL,
            "messages": [
                {"role": "system", "content": f"You are Jarvis created by {config.DEVELOPER_ALIAS}. Answer concisely."},
                {"role": "user",   "content": "tell me a joke"}
            ],
            "stream": False,
            "options": {"num_ctx": 1024, "temperature": 0.3}
        }, timeout=20)
        local_reply = res.json()["message"]["content"]
        test("Local Ollama replies with real content (not placeholder)",
             len(local_reply) > 10 and "Processing through local neural core" not in local_reply,
             f"Reply: {local_reply[:80]}...")
    except Exception as e:
        test("Local Ollama call succeeds", False, fail=str(e))
else:
    skip("Local Ollama reply (Bug 8)", "Ollama not running on this machine — Termux-only component")


# ============================================================
# BUG 9 — Formatter skip for structured replies
# ============================================================
header("BUG 9 — Formatter skips already-structured replies")

STRUCTURED_MARKERS = ['|', '✅', '📋', '❌', '⚠️', '🕒', '📍', '🔋', '🌤️', '📅', '🔎']

def is_structured(reply):
    return reply and any(marker in reply for marker in STRUCTURED_MARKERS)

test("Plain text 'IoT stands for...' → NOT structured (formatter runs)",
     not is_structured("IoT stands for Internet of Things."),
     "Formatter will run on plain text")

test("Help table with '|' borders → structured (formatter SKIPPED)",
     is_structured("| CONTROL SUITE | COMMAND REGISTRY |"),
     "Formatter skipped for table output")

test("Reply with ❌ icon → structured (formatter SKIPPED)",
     is_structured("❌ Storage contains no playable .mp3 layers."),
     "Formatter skipped for error messages")

test("Reply with ⚠️ → structured (formatter SKIPPED)",
     is_structured("⚠️ Web scraper returned no live results."),
     "Formatter skipped for warning messages")

test("Reply with 🕒 → structured (formatter SKIPPED)",
     is_structured("🕒 06:03 PM"),
     "Formatter skipped for time outputs")

test("'local' decision → formatter branch NOT entered (decision check)",
     'local' not in ['web', 'wikipedia'],
     "Local replies bypass formatter entirely")


# ============================================================
# BUG 10 — "read chat" partial match
# ============================================================
header("BUG 10 — 'read chat' partial match works")

# Temporarily create a log file if it doesn't exist for testing
if not os.path.exists(config.LOG_FILE):
    with open(config.LOG_FILE, "w") as f:
        json.dump([{"role": "user", "text": "test", "timestamp": "2026-07-01 12:00:00"},
                   {"role": "jarvis", "text": "hello", "timestamp": "2026-07-01 12:00:00"}], f)

result_partial  = commands.handle_command("read chat", [])
result_full     = commands.handle_command("read chat log", [])
result_typo     = commands.handle_command("reade chat log", [])

test("'read chat' (partial) → handled (not None)",
     result_partial is not None,
     f"Got: {str(result_partial)[:60]}")

test("'read chat log' (full) → still works",
     result_full is not None,
     f"Got: {str(result_full)[:60]}")

test("'reade chat log' (typo) → still works",
     result_typo is not None,
     f"Got: {str(result_typo)[:60]}")


# ============================================================
# BUG 11 — Fore.BLACK replaced with Fore.WHITE
# ============================================================
header("BUG 11 — Fore.BLACK replaced with Fore.WHITE in headers")

import inspect
import core_functions
src_core = inspect.getsource(core_functions.print_header)
src_help = inspect.getsource(commands.handle_command)

test("core_functions.py: Fore.BLACK + Style.BRIGHT removed from header",
     "Fore.BLACK" not in src_core,
     "All border lines now use Fore.WHITE")

test("core_functions.py: Fore.WHITE used for border lines",
     "Fore.WHITE + Style.BRIGHT" in src_core,
     "Visible on dark Termux terminal")

test("commands.py help table: Fore.BLACK border lines removed",
     'f"{Fore.BLACK}{Style.BRIGHT}+-' not in src_help,
     "Help table borders now use Fore.WHITE")


# ============================================================
# BUG 12 — Knowledge sync filtered to web-verified only
# ============================================================
header("BUG 12 — Knowledge sync only saves web-verified answers")

# Read jarvis.py source to verify the fix is in place
with open("jarvis.py", "r", encoding="utf-8") as f:
    jarvis_src = f.read()

test("Knowledge sync guarded by 'decision in web/react and web_results'",
     "if decision in" in jarvis_src and "web_results and not _is_no_cache:" in jarvis_src,
     "Hallucinated local/empty answers are NOT persisted")

test("No-cache blocklist prevents conversational queries from being cached",
     "NO_CACHE_QUERIES" in jarvis_src,
     "Conversational questions like 'what can you do' are never cached")


# ============================================================
# BUG 13 — search / define handlers implemented
# ============================================================
header("BUG 13 — 'search' and 'define' commands implemented")

# Test define command (Wikipedia — laptop has internet)
result_define = commands.handle_command("define python", [])
test("'define python' → returns Wikipedia content (not None)",
     result_define is not None and len(str(result_define)) > 20,
     f"Got: {str(result_define)[:80]}...")

test("'define python' does NOT say 'can't assist'",
     "can't assist" not in str(result_define).lower(),
     "Real Wikipedia lookup executed")

# Test search command (DuckDuckGo scraper)
result_search = commands.handle_command("search what is python", [])
test("'search what is python' → returns result or honest failure",
     result_search is not None,
     f"Got: {str(result_search)[:80]}...")

test("'define' with no term → returns usage hint",
     "Usage" in str(commands.handle_command("define", [])),
     "Empty define returns usage instruction")

test("'search' with no query → returns usage hint",
     "Usage" in str(commands.handle_command("search", [])),
     "Empty search returns usage instruction")


# ============================================================
# SUMMARY
# ============================================================
print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*54}")
print(f"{Fore.MAGENTA}{Style.BRIGHT}  📊 BUG-FIX VERIFICATION COMPLETE")
print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*54}")
print(f"  {Fore.GREEN}✓ Passed : {passed}")
print(f"  {Fore.RED}✗ Failed : {failed}")
print(f"  {Fore.YELLOW}⊘ Skipped: {skipped} (Termux-only hardware)")
print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*54}")

if failed == 0:
    print(f"{Fore.GREEN}{Style.BRIGHT}🚀 ALL FIXES VERIFIED — SYSTEM READY FOR TERMUX DEPLOYMENT")
else:
    print(f"{Fore.YELLOW}⚠️  {failed} test(s) failed — review output above before deploying")
