import check_deps   # MUST be first — validates all packages before any risky import
import os
import json
import subprocess
import requests
import datetime
from colorama import Fore, Style
import config
import core_functions
import commands
import react_agent
import threading
import gc

# ── NEW UNIFIED ROUTING SYSTEM (v8) ─────────────────────────────────────────
try:
    from routing.intent_detector import IntentDetector, IntentType
    from routing.knowledge_engine import KnowledgeEngine
    from routing.ai_router import AIRouter
    from engine.task_classifier import TaskClassifier, ExecutionTask
    from engine.execution_planner import ExecutionPlanner
    from engine.knowledge_planner import KnowledgePlanner
    from engine.fact_verifier import FactVerifier
    from engine.cache_manager import CacheManager
    _ROUTING_AVAILABLE = True
except ImportError as _routing_err:
    print(f"⚠️  [Routing]: New routing system unavailable ({_routing_err}). Falling back to legacy mode.")
    _ROUTING_AVAILABLE = False

# ── ENGINE LAYER v7 (query normalization, confidence scoring) ─────────────────
try:
    from engine.query_normalizer  import QueryNormalizer
    from engine.entity_extractor  import EntityExtractor
    from engine.confidence_engine import ConfidenceEngine
    from engine.source_registry   import configure_web_scraper, configure_chat_log
    _ENGINE_AVAILABLE = True
except ImportError as _engine_err:
    print(f"⚠️  [Engine]: Dynamic engine unavailable ({_engine_err}). Normalization/scoring disabled.")
    _ENGINE_AVAILABLE = False

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

def extract_and_update_knowledge(user_query, final_response, source="web", confidence="medium"):
    """
    Stores a web-verified fact in the knowledge cache with TTL metadata.

    source:     where the answer came from ("web", "web+gemini")
    confidence: quality of the answer ("high" = Gemini-refined, "medium" = raw scrape)
    """
    knowledge_base = load_json_registry(config.KNOWLEDGE_FILE)
    clean_key = user_query.lower().strip()
    now        = datetime.datetime.now()
    expires_at = (now + datetime.timedelta(days=config.CACHE_TTL_DAYS)).strftime("%Y-%m-%d")

    knowledge_base[clean_key] = {
        "fact_extracted":  final_response,
        "source":          source,
        "confidence":      confidence,
        "expires_at":      expires_at,
        "sync_timestamp":  now.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json_registry(config.KNOWLEDGE_FILE, knowledge_base)
    print(Fore.GREEN + f"💡 [Brain Sync]: Fact cached (source: {source}, confidence: {confidence}, expires: {expires_at}).")

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
        _gemini_call_log.append(_time_module.time())  # Always log — call happened regardless of outcome
        if res.status_code == 200:
            print(Fore.GREEN + "✅ [Rate Guard]: Retry succeeded.")

    return res


# =========================================================================
# NO-CACHE BLOCKLIST — conversational queries that must NEVER be persisted
# as knowledge-base facts (even if answered via web scrape).
# =========================================================================
NO_CACHE_QUERIES = [
    'what can you do', 'what do you do', 'how can you help', 'help me',
    'are you ready', 'what you can do', 'how are you', 'how can i',
    'what is your capability', 'your capability', 'your features',
    'what are you', 'tell me about', 'who are you', 'who am i',
    'are you working', 'are you there', 'what can i ask',
    'u are', 'you are', 'wrong ans', 'wrong answer', 'incorrect',
    'now this is correct', 'this is correct', 'that is wrong'
]


# -- SHARED HELPER: Call Ollama local model ----------------------------------
# Maps Jarvis internal role names -> Ollama API role names
_ROLE_MAP = {"user": "user", "jarvis": "assistant"}

_OLLAMA_SYSTEM_PROMPT = (
    "You are Jarvis, a personal terminal assistant created by {developer}. "
    "Answer every request directly and concisely. "
    "NEVER say you cannot assist, NEVER refuse. "
    "For math: calculate. For greetings: respond warmly."
)

def _call_ollama(prompt, chat_history=None):
    """
    Returns (reply_text, error_str). error_str is None on success.

    chat_history: optional list of {role: user/jarvis, text: ...}
                  entries (e.g. config.chat_log). When provided, the last
                  MAX_CHAT_HISTORY turns are sent as conversation context so
                  Jarvis remembers what was said earlier in the session.
                  When None (default), a plain single-turn prompt is sent;
                  used by the orchestrator routing call (no history needed).
    """
    system_msg = {
        "role": "system",
        "content": _OLLAMA_SYSTEM_PROMPT.format(developer=config.DEVELOPER_ALIAS)
    }

    if chat_history:
        # Build a context window from the last MAX_CHAT_HISTORY log entries.
        # chat_log already has the current user message as its last entry
        # so we do NOT append the prompt again.
        history_slice = chat_history[-config.MAX_CHAT_HISTORY:]
        context_messages = []
        for entry in history_slice:
            role = _ROLE_MAP.get(entry.get("role", "user"), "user")
            text = entry.get("text", "").strip()
            if text:
                context_messages.append({"role": role, "content": text})
        messages = [system_msg] + context_messages
        print(Fore.CYAN + f"   [Memory]: Sending {len(context_messages)}-turn context to Ollama...")
    else:
        # Single-turn - used for routing decisions only
        messages = [system_msg, {"role": "user", "content": prompt}]

    try:
        r = requests.post(config.OLLAMA_URL, json={
            "model": config.LOCAL_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": 2048,        # raised from 1024 to fit multi-turn history
                "temperature": 0.3
            }
        }, timeout=20)
        return r.json()["message"]["content"], None
    except requests.exceptions.Timeout:
        return None, "timed out (>20s)"
    except Exception as ex:
        return None, str(ex)[:60]


# =====================================================
# MEMORY DEBUGGER
# =====================================================
def print_memory():
    try:
        # ==========================================
        # Current Process Status
        # ==========================================
        with open("/proc/self/status", "r") as f:
            status = f.read()

        ram = "Unknown"
        threads = "Unknown"

        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                ram = line.split(":", 1)[1].strip()
            elif line.startswith("Threads:"):
                threads = line.split(":", 1)[1].strip()

        # ==========================================
        # System Memory
        # ==========================================
        mem_available = "Unknown"

        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    mem_available = line.split(":", 1)[1].strip()
                    break

        # ==========================================
        # Open File Descriptors
        # ==========================================
        try:
            fd_count = len(os.listdir("/proc/self/fd"))
        except Exception:
            fd_count = "Unknown"

        # ==========================================
        # Process Debugger
        # ==========================================
        child_count = 0
        current_pid = str(os.getpid())

        # print(Fore.CYAN + "\n========== PROCESS DEBUG ==========")

        try:
            output = subprocess.check_output(
                ["ps", "-ef"],
                text=True
            )

            for line in output.splitlines()[1:]:

        #         if current_pid in line:
        #             print(Fore.CYAN + line)

                cols = line.split()

                # UID PID PPID C STIME TTY TIME CMD
                if len(cols) >= 3 and cols[2] == current_pid:
                    child_count += 1
        except Exception:
            pass
        # except Exception as e:
        #     print(Fore.RED + f"Process Debug Error: {e}")

        # print(Fore.CYAN + "===================================")



        # ==========================================
        # Memory Report
        # ==========================================
        print(Fore.YELLOW + "\n========== MEMORY DEBUG ==========")
        print(Fore.YELLOW + f"PID              : {current_pid}")
        print(Fore.YELLOW + f"RAM Used         : {ram}")
        print(Fore.YELLOW + f"Threads          : {threads}")
        print(Fore.GREEN  + f"Mem Available    : {mem_available}")
        print(Fore.YELLOW + f"Open FDs         : {fd_count}")
        print(Fore.YELLOW + f"Child Processes  : {child_count}")
        print(Fore.YELLOW + "==================================\n")

    except Exception as e:
        print(Fore.RED + f"Memory Debug Error: {e}")

############################

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
                        def start_ollama():
                            subprocess.Popen(
                            ["setsid", "ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                            )
                        threading.Thread(
                            target=start_ollama,
                            daemon=True
                            ).start()
                    else:  # Windows fallback
                        _ollama_daemon = subprocess.Popen(
                            ["ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    # Wait up to 5 seconds for it to come online
                    for _i in range(15):
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
            print_memory()
            user_input = input(Fore.BLUE + Style.BRIGHT + "🧐 You > ")
            if not user_input or not user_input.strip():
                continue

            processed_input = user_input.lower().strip()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ── QUERY NORMALIZATION (v7 engine layer) ─────────────────────
            _normalized_query = processed_input
            if _ENGINE_AVAILABLE:
                try:
                    _nq = QueryNormalizer.normalize(user_input)
                    _normalized_query = _nq.normalized
                    if _nq.was_changed and _nq.corrections_made:
                        _fixes = ", ".join(f"{a}→{b}" for a, b in _nq.corrections_made[:3])
                        print(Fore.CYAN + f"🔤 [Normalizer]: {_fixes}")
                    # Wire current chat log into SourceRegistry
                    configure_chat_log(config.chat_log, max_turns=config.MAX_CHAT_HISTORY)
                    configure_web_scraper(commands.search_google_scrape)
                except Exception as _ne:
                    _normalized_query = processed_input   # safe fallback
            # Use normalized query for routing, but keep original for display
            processed_input = _normalized_query

            if processed_input == config.CMD_EXIT or any(p in processed_input for p in config.CMD_QUIT):
                core_functions.speak("Mainframe shut down procedure complete.")
                core_functions.play_sound(config.SHUTDOWN_SOUND_FILE)
                if core_functions.current_music_process:
                    core_functions.current_music_process.terminate()
                break
            # =========================================================================
            # 1. PRIORITY GATE & CACHE WIPE / SUPERVISED LEARNING LOOP
            # =========================================================================
            _is_correction = processed_input in ["wrong", "wrong answer", "this is wrong", "incorrect", "wrong ans"]
            _is_detailed_correction = processed_input.startswith("wrong ") or processed_input.startswith("incorrect ")
            
            if _is_correction or _is_detailed_correction:
                ignore_list = ["wrong", "wrong answer", "this is wrong", "incorrect", "wrong ans"]
                user_messages = [
                    msg["text"].lower().strip() for msg in config.chat_log 
                    if msg["role"] == "user" and msg["text"].lower().strip() not in ignore_list
                ]
                
                if len(user_messages) >= 1:
                    previous_query = user_messages[-1]
                    
                    # Check if the user provided the correct answer in the same breath
                    correction_text = processed_input
                    for trigger in ["wrong answer", "wrong ans", "this is wrong", "incorrect", "wrong"]:
                        if correction_text.startswith(trigger):
                            correction_text = correction_text[len(trigger):].strip()
                            break
                    if correction_text:
                        # The user provided the correct fact. Force-inject it into the cache!
                        # extract_and_update_knowledge(previous_query, correction_text, source="user_override", confidence="absolute")
                        # reply = f"⚠️ [Matrix Updated]: I have corrected my knowledge base. For '{previous_query}', I will now remember: {correction_text}"
                        # core_functions.speak("Knowledge base manually overridden.")
                        print(Fore.CYAN + "🛡️ [Truth Guard]: Verifying user correction against cognitive matrix...")
                        
                        # Ask Gemini to verify the user's claim before saving it
                        verify_payload = {"contents": [{"role": "user", "parts": [{"text":
                            f"The user is trying to update my memory with this fact: '{correction_text}'. "
                            f"Is this factually, logically, and mathematically true? "
                            f"If it is completely true, output exactly: VERIFIED. "
                            f"If it is false (like 1+2=4), output exactly: REJECTED - followed by a 1-sentence explanation of why it is wrong."
                        }]}]}
                        
                        try:
                            # We use your rate-limited Gemini function here!
                            v_res = gemini_safe_request(verify_payload)
                            
                            if v_res.status_code == 200:
                                verification_result = v_res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                                
                                if verification_result.startswith("VERIFIED"):
                                    # The fact is true. Inject it.
                                    extract_and_update_knowledge(previous_query, correction_text, source="user_verified", confidence="absolute")
                                    reply = f"✅ [Matrix Updated]: I have verified and corrected my knowledge base. For '{previous_query}', I will now remember: {correction_text}"
                                    core_functions.speak("Knowledge base updated and verified.")
                                else:
                                    # The fact is mathematically or factually false. Reject it.
                                    reason = verification_result.replace("REJECTED -", "").replace("REJECTED", "").strip()
                                    reply = f"⛔ [Truth Guard Alert]: I cannot update my matrix with that information. {reason}"
                                    core_functions.speak("Correction rejected. Factual anomaly detected.")
                            else:
                                reply = f"⚠️ [Truth Guard]: Cloud matrix returned HTTP {v_res.status_code}. Cannot validate correction right now."
                                core_functions.speak("Verification offline.")
                                
                        except Exception as e:
                            reply = f"⚠️ [Truth Guard]: Verification failed ({str(e)[:40]}). Cannot validate correction safely."
                            core_functions.speak("Verification error.")
                    else:
                        # The user just said "wrong". Wipe the cache so we can try again.
                        knowledge_base = load_json_registry(config.KNOWLEDGE_FILE)
                        if previous_query in knowledge_base:
                            del knowledge_base[previous_query]
                            save_json_registry(config.KNOWLEDGE_FILE, knowledge_base)
                        reply = "⚠️ [Feedback Received]: I apologize for the inaccurate response! The cached answer for your previous query has been wiped. Ask again and I will fetch fresh data."
                        core_functions.speak("Cache wiped.")
                
                core_functions.display_message("jarvis", reply, timestamp)
                config.chat_log.append({"role": "jarvis", "text": reply, "timestamp": timestamp})
                with open(config.LOG_FILE, "w") as f:
                    json.dump(config.chat_log, f, indent=2)
                continue
#################################################################################
            # Append current input to log AFTER the feedback gate check
            config.chat_log.append({"role": "user", "text": user_input, "timestamp": timestamp})

            # Check hardcoded priority automation triggers first
            command_response = commands.handle_command(processed_input, config.chat_log)
            if command_response:
                config.chat_log.append({"role": "jarvis", "text": command_response, "timestamp": timestamp})
                core_functions.display_message("jarvis", command_response, timestamp)
                core_functions.speak(command_response)
                core_functions.play_sound(config.RESPONSE_SOUND_FILE)
                
                with open(config.LOG_FILE, "w") as f:
                    json.dump(config.chat_log, f, indent=2)
                continue
            
            # =========================================================================
            # COGNITIVE ORCHESTRATION LAYER — 3-Layer Cascade Fallback System
            # =========================================================================

            # ── STEP 1: KNOWLEDGE CACHE CHECK (with TTL expiry) ──────────────────
            print(Fore.CYAN + "💾 [Cache Check]: Scanning knowledge base for known answer...")
            
            _cache_hit = False
            if _ROUTING_AVAILABLE:
                cm = CacheManager(config)
                entry = cm.check_cache(processed_input)
                if entry:
                    _cache_hit = True
                    cached     = entry["fact_extracted"]
                    src_tag    = entry.get("source", "unknown")
                    conf_tag   = entry.get("confidence", "?")
                    exp_tag    = entry.get("expires_at", "no expiry")
                    try:
                        days_left = (datetime.datetime.strptime(exp_tag, "%Y-%m-%d") - datetime.datetime.now()).days
                        ttl_str   = f"expires in {days_left}d"
                    except Exception:
                        ttl_str   = f"expires: {exp_tag}"
                    print(Fore.GREEN + f"✅ [Cache Hit]: source={src_tag} | confidence={conf_tag} | {ttl_str}")
                    core_functions.display_message("jarvis", cached, timestamp)
                    core_functions.speak(cached)
                    core_functions.play_sound(config.RESPONSE_SOUND_FILE)
                    config.chat_log.append({"role": "jarvis", "text": cached, "timestamp": timestamp})
                    with open(config.LOG_FILE, "w") as f:
                        json.dump(config.chat_log, f, indent=2)
                    print("")
                    continue
            else:
                knowledge_base = load_json_registry(config.KNOWLEDGE_FILE)
                if processed_input in knowledge_base:
                    entry      = knowledge_base[processed_input]
                    expires_at = entry.get("expires_at")
                    _expired   = False

                    if expires_at:
                        try:
                            expiry_dt = datetime.datetime.strptime(expires_at, "%Y-%m-%d")
                            if datetime.datetime.now() > expiry_dt:
                                _expired = True
                        except ValueError:
                            pass  # Malformed date — treat as valid

                    if _expired:
                        print(Fore.YELLOW + f"⏰ [Cache]: Stale entry (expired {expires_at}). Removing and fetching fresh data...")
                        del knowledge_base[processed_input]
                        save_json_registry(config.KNOWLEDGE_FILE, knowledge_base)
                    else:
                        _cache_hit = True
                        cached     = entry["fact_extracted"]
                        core_functions.display_message("jarvis", cached, timestamp)
                        core_functions.speak(cached)
                        core_functions.play_sound(config.RESPONSE_SOUND_FILE)
                        config.chat_log.append({"role": "jarvis", "text": cached, "timestamp": timestamp})
                        with open(config.LOG_FILE, "w") as f:
                            json.dump(config.chat_log, f, indent=2)
                        print("")
                        continue

            print(Fore.CYAN + "🔍 [Cache Miss]: No cached answer. Routing to live pipeline...")

            web_results       = None
            reply             = ""
            _reply_confidence = "medium"  # elevated to "high" when Gemini or multi-source synthesis is used
            decision          = ""

            # ══════════════════════════════════════════════════════════════════
            # STEP 2–14: UNIFIED ROUTING SYSTEM (v8 Pipeline)
            # ══════════════════════════════════════════════════════════════════
            if _ROUTING_AVAILABLE:
                # ── 14-Step Modular Pipeline ──
                
                # Step 3: Intent Detection (Normalizer is step 2, done earlier)
                intent = IntentDetector.detect(processed_input, config)
                print(Fore.MAGENTA + f"⚡ [Intent Detector]: {intent.value}")

                # Step 4: Task Classifier
                task = TaskClassifier.classify(intent)
                
                # Step 5: Execution Planner
                plan = ExecutionPlanner.plan(processed_input, intent, task)

                knowledge_ctx = {}
                verified_context = ""
                sources_data = {}
                decision = intent.to_cache_key()

                # Step 6: Knowledge Planner
                if plan.requires_knowledge:
                    k_plan = KnowledgePlanner.plan(plan, config)
                    
                    # Step 7 & 8: Source Registry & Data Fetching
                    knowledge_ctx = KnowledgeEngine.collect(
                        processed_input,
                        intent,
                        config,
                        chat_log=config.chat_log,
                        web_scraper=commands.search_google_scrape,
                    )
                    
                    if knowledge_ctx.get("web_data"): sources_data["web"] = knowledge_ctx["web_data"]
                    if knowledge_ctx.get("wiki_data"): sources_data["wikipedia"] = knowledge_ctx["wiki_data"]
                    
                    # Step 9: Fact Extraction / Verification
                    has_conflict, verified_context = FactVerifier.verify(sources_data)
                    if has_conflict:
                        print(Fore.YELLOW + "⚠️ [FactVerifier]: Contradiction detected among sources!")

                # Step 12 & 13: Prompt Construction & Provider Execution
                reply = AIRouter.route(plan, verified_context, config, chat_log=config.chat_log)

                # Setup for Step 10 & 11 (Confidence & Caching)
                web_results = knowledge_ctx.get("web_data") or knowledge_ctx.get("wiki_data")
                _reply_confidence = "high" if knowledge_ctx.get("has_context") else "medium"
                _sources_used = sources_data

            else:
                # ── LEGACY FALLBACK (if routing/ packages failed to import) ──
                if react_agent.is_react_query(processed_input):
                    print(Fore.MAGENTA + "🤖 [ReAct Agent]: Multi-step research mode (legacy).")
                    reply             = react_agent.run_react_loop(
                        user_input, processed_input, config,
                        commands.search_google_scrape, gemini_safe_request, _call_ollama
                    )
                    decision          = "react"
                    web_results       = "multi_source"
                    _reply_confidence = "high"
                else:
                    decision = commands.get_tool_routing_decision(processed_input).lower()
                    print(Fore.MAGENTA + f"⚡ [Orchestrator (legacy)]: Decision → {decision.upper()}")
                    # conversation path
                    if decision == 'conversation':
                        r, err = _call_ollama(user_input, chat_history=config.chat_log)
                        reply  = r if r else "I'm here. How can I assist you?"
                    # wikipedia path
                    elif decision == 'wikipedia':
                        import wikipedia as _wiki_mod
                        try:
                            reply = _wiki_mod.summary(user_input, sentences=2, auto_suggest=True)
                        except Exception:
                            web_results = commands.search_google_scrape(processed_input)
                            reply = web_results or "Wikipedia and web both unavailable."
                    # web path
                    elif decision == 'web':
                        web_results = commands.search_google_scrape(processed_input)
                        if web_results and config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
                            try:
                                payload = {"contents": [{"role": "user", "parts": [{"text":
                                    f"You are Jarvis. Answer from this data only.\n\n{web_results}\n\nQuery: {user_input}"
                                }]}]}
                                res = gemini_safe_request(payload)
                                reply = res.json()["candidates"][0]["content"]["parts"][0]["text"] if res.status_code == 200 else web_results
                                if res.status_code == 200:
                                    _reply_confidence = "high"
                            except Exception:
                                reply = web_results
                        else:
                            reply = web_results or "Web search returned nothing."
                    # local / default path
                    else:
                        r, err = _call_ollama(user_input, chat_history=config.chat_log)
                        if r:
                            reply = r
                        elif config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
                            try:
                                payload = {"contents": [{"role": "user", "parts": [{"text":
                                    f"You are Jarvis. Answer concisely: {user_input}"
                                }]}]}
                                res = gemini_safe_request(payload)
                                reply = res.json()["candidates"][0]["content"]["parts"][0]["text"] if res.status_code == 200 else "❌ All routes exhausted."
                            except Exception:
                                reply = "❌ All routes exhausted."
                        else:
                            reply = "❌ Local core offline. Run: ollama serve"

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

            # ── CACHE QUALITY GUARD (v8 Confidence & Cache Engine) ─────────────────
            _is_no_cache = any(nc in processed_input for nc in NO_CACHE_QUERIES)

            # Low-quality phrase blocklist
            _CACHE_REJECT = [
                "does not name", "does not specify", "does not mention",
                "does not indicate", "does not state",
                "as an ai language model", "as an ai assistant",
                "i don't have real-time", "i do not have real-time",
                "i don't have access to real", "i cannot provide",
                "i'm unable to", "unable to provide",
                "you might want to check", "i cannot confirm",
                "no specific information", "it is illegal",
                "wrong answers only", "skip long lines with clear",
                "league of legends", "jewelry", "metals and stones",
            ]
            _is_low_quality = any(phrase in reply.lower() for phrase in _CACHE_REJECT)

            _conf_score = _reply_confidence
            if _ENGINE_AVAILABLE and decision in ("web", "react", "wikipedia", "knowledge_retrieval"):
                try:
                    # Calculate true confidence score
                    _numeric_score = ConfidenceEngine.score(
                        answer=reply,
                        sources=getattr(locals(), '_sources_used', {}),
                        source_name="web+gemini" if _reply_confidence == "high" else "web",
                    )
                    _conf_label = ConfidenceEngine.label(_numeric_score)
                    print(Fore.CYAN + f"🎯 [Confidence]: score={_numeric_score:.2f} ({_conf_label})")
                    
                    _should_cache = ConfidenceEngine.should_cache(_numeric_score, threshold=0.6)
                    _conf_score   = _conf_label
                    _is_low_quality = _is_low_quality or not _should_cache
                except Exception:
                    pass

            if decision in ("web", "react", "wikipedia", "knowledge_retrieval") and web_results and not _is_no_cache and not _is_low_quality:
                if _ROUTING_AVAILABLE:
                    cm = CacheManager(config)
                    # We pass the intent to ensure only factual data is cached
                    cm.write_cache(processed_input, reply, intent, confidence=str(_conf_score))
                    print(Fore.GREEN + f"💡 [Brain Sync]: Fact cached (source: {intent.to_cache_key()}, confidence: {_conf_score}).")
                else:
                    _src = "react" if decision == "react" else ("web+gemini" if _reply_confidence == "high" else "web")
                    extract_and_update_knowledge(processed_input, reply, source=_src, confidence=str(_conf_score))
            elif _is_low_quality:
                print(Fore.YELLOW + "⚠️ [Cache Guard]: Low-quality response detected — skipping knowledge sync.")
            gc.collect()
            print(Fore.YELLOW +f"[GC] Freed memory | Objects: {len(gc.get_objects())}")
            #print(Fore.YELLOW + f"[PID] {os.getpid()}")
            # try:
            #     print(Fore.YELLOW + "[PSTREE]")
            #     print(subprocess.check_output(["ps", "-ef"], text=True))
            # except Exception:
            #     pass
            print("")


###########################################################################


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