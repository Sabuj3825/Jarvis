import check_deps   # MUST be first — validates all packages before any risky import
import os
import json
import requests
import datetime
from colorama import Fore, Style
import config
import core_functions
import commands

def load_json_registry(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} if "knowledge" in file_path else []
    return {} if "knowledge" in file_path else []

def save_json_registry(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def extract_and_update_knowledge(user_query, final_response):
    """Parses output states asynchronously and merges atomic data facts into knowledge stores."""
    knowledge_base = load_json_registry(config.KNOWLEDGE_FILE)
    clean_key = user_query.lower().strip()
    
    knowledge_base[clean_key] = {
        "fact_extracted": final_response,
        "sync_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json_registry(config.KNOWLEDGE_FILE, knowledge_base)
    print(Fore.GREEN + f"💡 [Brain Sync]: Advanced fact learned and committed to knowledge matrix.")

# =========================================================================
# GEMINI SAFE REQUEST — Rate Guard (prevents 429 before it happens)
# Free tier limit: 15 req/min → we use 14 max (safety margin)
# Min interval: 60s / 14 = 4.3s between calls
# =========================================================================
import time as _time_module
_gemini_call_log = []          # timestamps of recent Gemini calls
_GEMINI_RPM_SAFE  = 14         # stay under 15 RPM
_GEMINI_MIN_GAP   = 4.3        # seconds minimum between calls

def gemini_safe_request(payload):
    """
    Rate-limited Gemini POST. Prevents 429 by:
    1. Enforcing 4.3s minimum gap between consecutive calls
    2. Waiting if 14+ calls made in the last 60s
    3. Auto-retrying ONCE with 62s backoff if 429 still occurs
    Returns: requests.Response object
    """
    global _gemini_call_log
    now = _time_module.time()

    # Prune timestamps older than 60 seconds
    _gemini_call_log = [t for t in _gemini_call_log if now - t < 60]

    # Check: are we near the per-minute limit?
    if len(_gemini_call_log) >= _GEMINI_RPM_SAFE:
        oldest   = _gemini_call_log[0]
        wait_sec = 60.0 - (now - oldest) + 1.0   # +1s safety buffer
        if wait_sec > 0:
            print(Fore.YELLOW + f"⏳ [Rate Guard]: {len(_gemini_call_log)} req/min limit reached. Waiting {wait_sec:.0f}s...")
            for remaining in range(int(wait_sec), 0, -1):
                print(Fore.YELLOW + f"   ⏱  {remaining}s remaining...", end="\r")
                _time_module.sleep(1)
            print("")

    # Check: enforce minimum gap between consecutive calls
    elif _gemini_call_log:
        elapsed = now - _gemini_call_log[-1]
        if elapsed < _GEMINI_MIN_GAP:
            gap = _GEMINI_MIN_GAP - elapsed
            print(Fore.CYAN + f"⏳ [Rate Guard]: Spacing call by {gap:.1f}s to stay under rate limit...")
            _time_module.sleep(gap)

    # Make the request
    res = requests.post(config.URL, headers=config.HEADERS, data=json.dumps(payload), timeout=20)
    _gemini_call_log.append(_time_module.time())

    # Auto-retry once on 429 (in case timing was off)
    if res.status_code == 429:
        retry_wait = 62
        print(Fore.YELLOW + f"⚠️  [Rate Guard]: Got 429. Auto-retrying in {retry_wait}s...")
        for remaining in range(retry_wait, 0, -1):
            print(Fore.YELLOW + f"   ⏱  Retry in {remaining}s...", end="\r")
            _time_module.sleep(1)
        print("")
        res = requests.post(config.URL, headers=config.HEADERS, data=json.dumps(payload), timeout=20)
        if res.status_code == 200:
            _gemini_call_log.append(_time_module.time())
            print(Fore.GREEN + "✅ [Rate Guard]: Retry succeeded.")

    return res


if __name__ == "__main__":
    core_functions.print_header()
    core_functions.play_sound(config.STARTUP_SOUND_FILE)
    
    # Mirror system logs across chat log trackers
    if os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, "r") as f:
            try: config.chat_log = json.load(f)
            except Exception: config.chat_log = []
    else:
        config.chat_log = []

   # Load previous conversations
    conversations_history = load_json_registry(config.CONVERSATIONS_FILE)

    if not isinstance(conversations_history, list):
         conversations_history = []

    # =========================================================================
    # AUTO-START OLLAMA DAEMON (signal-9 resilient)
    # =========================================================================
    # SIGKILL (signal 9) cannot be caught — Ollama is intentionally NOT killed
    # on Jarvis exit so it PERSISTS between sessions (faster restart, less RAM spike).
    # It runs detached from this process group — Android OOM targets Jarvis first.
    _ollama_daemon = None

    def _ollama_already_running():
        try:
            r = requests.get("http://127.0.0.1:11434", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def _free_ram_mb():
        """Returns approximate free RAM in MB. Works on Linux/Termux via /proc/meminfo."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024  # kB → MB
        except Exception:
            pass
        return 9999  # Unknown → assume enough (safe fallback for Windows)

    if not _ollama_already_running():
        free_ram = _free_ram_mb()
        if free_ram < 300:
            print(Fore.YELLOW + f"⚠️  [Ollama Daemon]: Low RAM ({free_ram}MB free). Skipping auto-launch to prevent OOM kill.")
            print(Fore.YELLOW + "   → Free up RAM, then run 'ollama serve' manually if needed.")
        else:
            print(Fore.CYAN + f"🤖 [Ollama Daemon]: Not detected ({free_ram}MB RAM free). Auto-launching...")
            try:
                import shutil as _shutil
                import time as _time
                if _shutil.which("ollama"):
                    # Use 'setsid' on Linux/Termux to detach daemon from this session group.
                    # This means Android OOM killer targets Jarvis (less RAM) first, not Ollama.
                    import platform as _platform
                    if _platform.system() == "Linux":
                        _ollama_daemon = subprocess.Popen(
                            ["setsid", "ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                    else:  # Windows fallback
                        _ollama_daemon = subprocess.Popen(
                            ["ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    # Wait up to 5 seconds for it to come online
                    for _i in range(5):
                        _time.sleep(1)
                        if _ollama_already_running():
                            print(Fore.GREEN + f"✅ [Ollama Daemon]: Online after {_i+1}s. Local core ready.")
                            break
                    else:
                        print(Fore.YELLOW + "⚠️  [Ollama Daemon]: Started but not responding yet. Continuing...")
                else:
                    print(Fore.YELLOW + "⚠️  [Ollama Daemon]: 'ollama' not found. Install: pkg install ollama")
            except Exception as _e:
                print(Fore.YELLOW + f"⚠️  [Ollama Daemon]: Auto-launch failed — {str(_e)[:60]}")
    else:
        print(Fore.GREEN + "✅ [Ollama Daemon]: Already running. Local core ready.")

    # SIGTERM handler — Android sends SIGTERM before SIGKILL (soft kill).
    # We flush logs here since the finally block won't run on SIGKILL.
    import signal as _signal
    def _sigterm_handler(signum, frame):
        print(Fore.YELLOW + "\n⚠️  [System]: SIGTERM received. Flushing logs before shutdown...")
        try:
            with open(config.LOG_FILE, "w") as _f:
                json.dump(config.chat_log, _f, indent=2)
            print(Fore.GREEN + "✅ [System]: Logs flushed safely.")
        except Exception:
            pass
        raise SystemExit(0)
    _signal.signal(_signal.SIGTERM, _sigterm_handler)

    print("")


    try:
        while True:
            user_input = input(Fore.BLUE + Style.BRIGHT + "🧐 You > ")
            if not user_input or not user_input.strip():
                continue

            processed_input = user_input.lower().strip()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if processed_input == config.CMD_EXIT or any(p in processed_input for p in config.CMD_QUIT):
                core_functions.speak("Mainframe shut down procedure complete.")
                core_functions.play_sound(config.SHUTDOWN_SOUND_FILE)
                if core_functions.current_music_process:
                    core_functions.current_music_process.terminate()
                break

            config.chat_log.append({"role": "user", "text": user_input, "timestamp": timestamp})

            # Check hardcoded priority automation triggers first
            command_response = commands.handle_command(processed_input, config.chat_log)
            if command_response:
                config.chat_log.append({"role": "jarvis", "text": command_response, "timestamp": timestamp})
                
                # --- FIXED: Corrected variable name from 'command_command_response' to 'command_response' ---
                core_functions.display_message("jarvis", command_response, timestamp)
                
                core_functions.speak(command_response)
                core_functions.play_sound(config.RESPONSE_SOUND_FILE)
                
                with open(config.LOG_FILE, "w") as f:
                    json.dump(config.chat_log, f, indent=2)
                continue
            
            # =========================================================================
            # COGNITIVE ORCHESTRATION LAYER — 3-Layer Cascade Fallback System
            # =========================================================================

            # ── SHARED HELPER: Call Ollama local model ────────────────────────────
            def _call_ollama(prompt):
                """Returns (reply_text, error_str). error_str is None on success."""
                try:
                    r = requests.post(config.OLLAMA_URL, json={
                        "model": config.LOCAL_MODEL,
                        "messages": [
                            {"role": "system", "content": (
                                f"You are Jarvis, a personal terminal assistant created by {config.DEVELOPER_ALIAS}. "
                                "Answer every request directly and concisely. "
                                "NEVER say you cannot assist, NEVER refuse. "
                                "For math: calculate. For greetings: respond warmly."
                            )},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "options": {"num_ctx": 1024, "temperature": 0.3}
                    }, timeout=20)
                    return r.json()["message"]["content"], None
                except requests.exceptions.Timeout:
                    return None, "timed out (>20s)"
                except Exception as ex:
                    return None, str(ex)[:60]

            # ── STEP 1: KNOWLEDGE CACHE CHECK ────────────────────────────────────
            print(Fore.CYAN + "💾 [Cache Check]: Scanning knowledge base for known answer...")
            knowledge_base = load_json_registry(config.KNOWLEDGE_FILE)
            if processed_input in knowledge_base:
                cached = knowledge_base[processed_input]["fact_extracted"]
                print(Fore.GREEN + "✅ [Cache Hit]: Serving answer from local knowledge matrix.")
                core_functions.display_message("jarvis", cached, timestamp)
                core_functions.speak(cached)
                core_functions.play_sound(config.RESPONSE_SOUND_FILE)
                config.chat_log.append({"role": "jarvis", "text": cached, "timestamp": timestamp})
                with open(config.LOG_FILE, "w") as f:
                    json.dump(config.chat_log, f, indent=2)
                print("")
                continue

            print(Fore.CYAN + "🔍 [Cache Miss]: No cached answer. Routing to live pipeline...")

            # ── STEP 2: ORCHESTRATOR DECISION ────────────────────────────────────
            decision = commands.get_tool_routing_decision(processed_input)
            print(Fore.MAGENTA + f"⚡ [Orchestrator]: Decision → {decision.upper()}")

            web_results = None
            reply = ""

            # ── STEP 3A: WIKIPEDIA PATH → fallback: WEB → fallback: LOCAL ────────
            if decision == 'wikipedia':
                import wikipedia
                print(Fore.CYAN + "📖 [Wikipedia]: Fetching encyclopedic entry...")
                try:
                    reply = wikipedia.summary(user_input, sentences=2, auto_suggest=True)
                    print(Fore.GREEN + "✅ [Wikipedia]: Entry retrieved successfully.")
                except Exception as e:
                    print(Fore.YELLOW + f"⚠️  [Wikipedia]: Failed — {str(e)[:60]}")
                    print(Fore.CYAN + "🔁 [Fallback L1]: Trying web scraper instead...")
                    web_results = commands.search_google_scrape(processed_input)
                    if web_results:
                        print(Fore.GREEN + "✅ [Fallback L1]: Web scraper returned data.")
                        reply = web_results
                    else:
                        print(Fore.YELLOW + "⚠️  [Fallback L1]: Web scraper also empty.")
                        print(Fore.CYAN + f"🔁 [Fallback L2]: Asking local Ollama '{config.LOCAL_MODEL}'...")
                        r, err = _call_ollama(user_input)
                        if r:
                            print(Fore.GREEN + "✅ [Fallback L2]: Ollama gave best-effort answer.")
                            reply = r
                        else:
                            print(Fore.RED + f"❌ [Fallback L2]: Ollama also failed — {err}")
                            reply = "❌ All pipeline routes failed. Wikipedia, Web scraper, and Local core are all unavailable."

            # ── STEP 3B: WEB PATH → fallback: LOCAL → fallback: GEMINI DIRECT ────
            elif decision == 'web':
                print(Fore.CYAN + "🌐 [Web Scraper]: Searching live network data...")
                web_results = commands.search_google_scrape(processed_input)

                if not web_results:
                    print(Fore.YELLOW + "⚠️  [Web Scraper]: No results returned. Network may be blocked.")
                    print(Fore.CYAN + f"🔁 [Fallback L1]: Asking local Ollama '{config.LOCAL_MODEL}'...")
                    r, err = _call_ollama(user_input)
                    if r:
                        print(Fore.GREEN + "✅ [Fallback L1]: Ollama gave best-effort answer.")
                        reply = r
                    else:
                        print(Fore.RED + f"⚠️  [Fallback L1]: Ollama also failed — {err}")
                        reply = "❌ Web scraper returned nothing and local core is offline."

                elif config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
                    print(Fore.GREEN + "✅ [Web Scraper]: Live data captured.")
                    print(Fore.CYAN + "📡 [Cloud Escalation]: Connecting to Gemini API matrix...")
                    try:
                        payload = {"contents": [{"role": "user", "parts": [{"text":
                            f"You are Jarvis, a terminal assistant created by {config.DEVELOPER_ALIAS}. "
                            f"Answer ONLY using the following scraped web data. Do NOT add extra info.\n\n"
                            f"Scraped Data: {web_results}\n\nQuery: {user_input}"
                        }]}]}
                        res = gemini_safe_request(payload)

                        if res.status_code == 429:
                            print(Fore.YELLOW + "⚠️  [Cloud Escalation]: Gemini rate limit hit (429). Serving raw web data.")
                            reply = web_results
                        elif res.status_code != 200:
                            print(Fore.YELLOW + f"⚠️  [Cloud Escalation]: Gemini error (HTTP {res.status_code}). Serving raw web data.")
                            reply = web_results
                        else:
                            reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                            print(Fore.GREEN + "✅ [Cloud Escalation]: Gemini response received.")

                    except requests.exceptions.Timeout:
                        print(Fore.YELLOW + "⚠️  [Cloud Escalation]: Gemini timed out (>20s). Serving raw web data.")
                        reply = web_results
                    except Exception as e:
                        print(Fore.YELLOW + f"⚠️  [Cloud Escalation]: Gemini failed — {str(e)[:60]}. Serving raw web data.")
                        reply = web_results
                else:
                    print(Fore.GREEN + "✅ [Web Scraper]: Live data captured.")
                    print(Fore.YELLOW + "💡 [Cloud Escalation]: No Gemini key. Serving raw web data directly.")
                    reply = web_results

            # ── STEP 3C: LOCAL PATH → fallback: GEMINI DIRECT ───────────────────
            else:
                print(Fore.CYAN + f"🧠 [Local Core]: Routing to Ollama '{config.LOCAL_MODEL}'...")
                r, err = _call_ollama(user_input)
                if r:
                    print(Fore.GREEN + "✅ [Local Core]: Ollama response received.")
                    reply = r
                else:
                    print(Fore.RED + f"⚠️  [Local Core]: Ollama failed — {err}")
                    if config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
                        print(Fore.CYAN + "🔁 [Fallback L1]: Ollama down. Escalating to Gemini...")
                        try:
                            payload = {"contents": [{"role": "user", "parts": [{"text":
                                f"You are Jarvis, a terminal assistant created by {config.DEVELOPER_ALIAS}. "
                                f"Answer concisely: {user_input}"
                            }]}]}
                            res = gemini_safe_request(payload)
                            if res.status_code == 200:
                                reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                                print(Fore.GREEN + "✅ [Fallback L1]: Gemini answered as Ollama backup.")
                            elif res.status_code == 429:
                                print(Fore.RED + "⚠️  [Fallback L1]: Gemini rate limit (429). All routes exhausted.")
                                reply = "❌ Local core offline + Gemini rate limited. Try again later."
                            else:
                                print(Fore.RED + f"⚠️  [Fallback L1]: Gemini error (HTTP {res.status_code}). All routes exhausted.")
                                reply = "❌ Local core offline + Gemini unavailable."
                        except Exception as e:
                            print(Fore.RED + f"⚠️  [Fallback L1]: Gemini also failed — {str(e)[:60]}")
                            reply = "❌ All pipeline routes exhausted. No response available."
                    else:
                        reply = "❌ Local core offline. No Gemini key set. Run: ollama serve"

            # NOTE: Ollama formatter removed — qwen2.5:0.5b was hallucinating factual content.




            # =========================================================================
            # CORE OUTPUT DISPLAY & WRITING INTERFACES
            # =========================================================================
            config.chat_log.append({"role": "jarvis", "text": reply, "timestamp": timestamp})
            core_functions.display_message("jarvis", reply, timestamp)
            core_functions.speak(reply)
            core_functions.play_sound(config.RESPONSE_SOUND_FILE)

            # Sync active session transcripts to conversations file
            conversations_history.append({"role": "user", "text": user_input, "timestamp": timestamp})
            conversations_history.append({"role": "jarvis", "text": reply, "timestamp": timestamp})
            save_json_registry(config.CONVERSATIONS_FILE, conversations_history)
            
            with open(config.LOG_FILE, "w") as f:
                json.dump(config.chat_log, f, indent=2)
            print(Fore.CYAN + f"📂 Log states written cleanly to '{config.CONVERSATIONS_FILE}' and '{config.LOG_FILE}'.")

            # Only persist to knowledge base when answer came from verified web scrape data
            # AND the query is a specific factual question (not generic/conversational)
            NO_CACHE_QUERIES = [
                'what can you do', 'what do you do', 'how can you help', 'help me',
                'are you ready', 'what you can do', 'how are you', 'how can i',
                'what is your capability', 'your capability', 'your features',
                'what are you', 'tell me about', 'who are you', 'who am i',
                'are you working', 'are you there', 'what can i ask',
            ]
            _is_no_cache = any(nc in processed_input for nc in NO_CACHE_QUERIES)
            if decision == 'web' and web_results and not _is_no_cache:
                extract_and_update_knowledge(user_input, reply)
            print("")

    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nExecution drop signal caught via interface. Safely closing mainframe channels.")
    finally:
        if core_functions.current_music_process and core_functions.current_music_process.poll() is None:
            core_functions.current_music_process.terminate()
        # Shutdown the Ollama daemon we auto-launched (if we started it)
        if _ollama_daemon and _ollama_daemon.poll() is None:
            print(Fore.CYAN + "🤖 [Ollama Daemon]: Shutting down auto-launched daemon...")
            _ollama_daemon.terminate()
            print(Fore.GREEN + "✅ [Ollama Daemon]: Daemon terminated cleanly.")