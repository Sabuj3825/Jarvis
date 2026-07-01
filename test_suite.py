import os
import json
import requests
import shutil  
import subprocess
from colorama import Fore, Style, init
import config
import commands

init(autoreset=True)

def run_test_suite():
    print(Fore.MAGENTA + Style.BRIGHT + "====================================================")
    print(Fore.MAGENTA + Style.BRIGHT + "🛰️  JARVIS FULL PIPELINE REPOSITORY DIAGNOSTIC")
    print(Fore.MAGENTA + Style.BRIGHT + "====================================================\n")

    passed = 0
    total_tests = 0

    def assert_test(name, condition, success_msg, fail_msg):
        nonlocal passed, total_tests
        total_tests += 1
        print(f"🔄 Testing Node: {Fore.YELLOW}{name}...")
        if condition:
            print(f"  {Fore.GREEN}✓ PASSED: {success_msg}")
            passed += 1
            return True
        else:
            print(f"  {Fore.RED}✗ FAILED: {fail_msg}")
            return False

    # =========================================================================
    # SECTION 1: CORE LOCAL FUNCTION GATES
    # =========================================================================
    print(Fore.CYAN + Style.BRIGHT + "🌐 [SECTION 1: PRIORITY AUTOMATION GATES]")
    
    assert_test(
        "Time Telemetry Output",
        len(str(commands.handle_command("time", []))) > 0,
        "System priority time data generated cleanly.",
        "Priority gate dropped or failed to calculate time parameters."
    )

    assert_test(
        "Branding Core Identity Protection",
        "Sabuj" in str(commands.handle_command("who made you", [])),
        "Identity shield locked to Sabuj De.",
        "Branding override missing or compromised."
    )

    assert_test(
        "Music String Typo Isolation",
        "Storage contains no" in str(commands.handle_command("play random muisic", [])),
        "Typo gateway trapped variance 'muisic' cleanly.",
        "Music typo fallback routine failed to match."
    )

    # =========================================================================
    # SECTION 2: BINARY ENVIRONMENT DRIVERS
    # =========================================================================
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[SECTION 2: BACKGROUND ENVIRONMENT DRIVERS]")

    assert_test(
        "Media Stream Streamer (yt-dlp)",
        shutil.which("yt-dlp") is not None,
        "yt-dlp package binary found in environment path array.",
        "yt-dlp package missing. Install it via: pip install yt-dlp"
    )

    assert_test(
        "Media Stream Controller (mpv)",
        shutil.which("mpv") is not None,
        "mpv system engine binary found in path.",
        "mpv utility engine missing. Install it via: pkg install mpv"
    )

    # =========================================================================
    # SECTION 3: LOCAL STORAGE PATH MATRIX
    # =========================================================================
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[SECTION 3: LOCAL STORAGE FILES & PATHS]")

    assert_test(
        "Music Directory Infrastructure",
        os.path.exists(config.MUSIC_DIR),
        f"Target directory array located at {config.MUSIC_DIR}",
        f"Directory block missing. Please build folder path at: {config.MUSIC_DIR}"
    )

    assert_test(
        "To-Do Matrix File Stream",
        (commands.handle_command("show tasks", []) is not None),
        "Task manager file operations running clean.",
        "JSON file serialization operations failed on disk."
    )

    # =========================================================================
    # SECTION 4: SERVER PORTS & NETWORK CONNECTIVITY (OLLAMA / GEMINI)
    # =========================================================================
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[SECTION 4: LOCAL PORTS & CLOUD MATRIX SUITE]")

    # Check Local Ollama Instance
    ollama_ok = False
    try:
        res = requests.get("http://127.0.0.1:11434", timeout=3)
        ollama_ok = (res.status_code == 200)
    except Exception:
        pass
    assert_test(
        "Local Ollama Core Daemon Socket",
        ollama_ok,
        "Ollama port 11434 is live and responding.",
        "Ollama server is offline. Run 'ollama serve' in your background tab."
    )

    # Check Scraper Web Link Vector
    scraper_res = commands.search_google_scrape("current year")
    assert_test(
        "Google Network Socket Crawler",
        scraper_res is not None and len(scraper_res) > 5,
        "Web crawler returned live text stream blocks.",
        "Google returned empty elements. Network blocked or anti-bot challenge active."
    )

    # Check Cloud Escalation Integration (Gemini Endpoint Validation)
    gemini_ok = False
    gemini_details = ""
    if config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
        try:
            test_payload = {
                "contents": [{"role": "user", "parts": [{"text": "Respond with single word: ONLINE"}]}]
            }
            g_res = requests.post(config.URL, headers=config.HEADERS, data=json.dumps(test_payload), timeout=8)
            
            # --- EXPLICIT 429 RATE LIMIT CHECK ADDED HERE ---
            if g_res.status_code == 200:
                gemini_ok = True
                gemini_details = g_res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif g_res.status_code == 429:
                gemini_ok = False
                gemini_details = "ERROR 429: RATE LIMIT EXCEEDED! (Wait 60 seconds before testing again)"
            else:
                gemini_details = f"HTTP Error Status {g_res.status_code}"
                
        except Exception as e:
            gemini_details = str(e)
    else:
        gemini_details = "API Key value string unpopulated in config.py"

    assert_test(
        "Gemini Matrix Link Platform Integration",
        gemini_ok,
        f"Cloud channel running smoothly. Response token: {gemini_details}",
        f"Cloud matrix link failed -> {gemini_details}"
    )

    # =========================================================================
    # DIAGNOSTIC SUMMARY REPORT
    # =========================================================================
    print("\n" + Fore.MAGENTA + Style.BRIGHT + "====================================================")
    print(f"📊 DIAGNOSTIC MATRIX COMPLETE: {Fore.GREEN}{passed}{Fore.WHITE} / {Fore.CYAN}{total_tests}{Fore.WHITE} COMPONENTS OK.")
    print(Fore.MAGENTA + Style.BRIGHT + "====================================================")
    
    if passed == total_tests:
        print(Fore.GREEN + Style.BRIGHT + "🚀 SYSTEM STATUS: GREEN MATRIX STABLE. FULL PROTOCOLS OPERATIONAL.")
    else:
        print(Fore.YELLOW + "⚠️  SYSTEM STATUS: REVIEW MISSED BLOCKS ABOVE BEFORE DEPLOYMENT.")

if __name__ == "__main__":
    run_test_suite()