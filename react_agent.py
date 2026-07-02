"""
react_agent.py — ReAct (Reasoning + Acting) Agent for Jarvis
=============================================================
Activated automatically when a query is detected as requiring
multi-step research (e.g. "research X and summarize", "compare A vs B").

Pipeline:
  Step 1 — PLAN:      Ask local model to generate optimised sub-queries
  Step 2 — WIKIPEDIA: Encyclopedic background knowledge
  Step 3 — WEB:       Live scrape for current / detailed information
  Step 4 — SYNTHESIZE: Gemini (preferred) or Ollama merges both sources
"""

import requests
from colorama import Fore, Style

# =========================================================================
# TRIGGER DETECTION
# =========================================================================
REACT_TRIGGER_WORDS = [
    "research", "summarize", "summary", "compare", "analyse", "analyze",
    "comprehensive", "overview", "deep dive", "pros and cons",
    "tell me everything", "in detail", "step by step", "thoroughly",
    "explain everything", "full explanation", "complete guide",
    "all about", "teach me", "breakdown", "break down", "differences between",
]

def is_react_query(processed_input):
    """
    Returns True when the query is complex enough for multi-step research.
    Requires: at least one trigger word AND at least 4 words total.
    """
    if len(processed_input.split()) < 4:
        return False
    return any(t in processed_input for t in REACT_TRIGGER_WORDS)


# =========================================================================
# STEP 1 — PLAN: Generate optimised sub-queries via local model
# =========================================================================
def _plan_subqueries(user_query, config):
    """
    Asks the local Ollama model to decompose the research request into:
      - A short Wikipedia search term  (encyclopedic, 2-4 words)
      - A detailed web search query    (current info, 5-8 words)

    Falls back to the original query for both if planning fails or times out.
    """
    prompt = (
        f"Break down this research request into two search queries.\n"
        f"Request: '{user_query}'\n\n"
        f"Reply with EXACTLY two lines, no other text:\n"
        f"WIKI: <2-4 word Wikipedia search term>\n"
        f"WEB: <5-8 word web search query>"
    )
    try:
        r = requests.post(config.OLLAMA_URL, json={
            "model":   config.LOCAL_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream":  False,
            "options": {"temperature": 0.0, "num_ctx": 512}
        }, timeout=8)
        raw   = r.json()["message"]["content"]
        wiki_q = web_q = user_query   # safe defaults
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("WIKI:"):
                wiki_q = line.split(":", 1)[1].strip() or user_query
            elif line.upper().startswith("WEB:"):
                web_q  = line.split(":", 1)[1].strip() or user_query
        return wiki_q, web_q
    except Exception:
        return user_query, user_query   # fallback: use original query for both


# =========================================================================
# MAIN REACT LOOP
# =========================================================================
def run_react_loop(user_input, processed_input, config,
                   search_google_scrape, gemini_safe_request, call_ollama_fn):
    """
    Executes the full ReAct pipeline and returns a synthesized reply string.

    Parameters:
      user_input          Original (uncleaned) user input
      processed_input     Lowercased, stripped version
      config              The config module (for API keys, model names, etc.)
      search_google_scrape  Web scraper function from commands.py
      gemini_safe_request   Rate-guarded Gemini POST function from jarvis.py
      call_ollama_fn        _call_ollama function from jarvis.py
    """
    import wikipedia as _wiki

    SEP = Fore.WHITE + "  " + "-" * 52
    print(Fore.MAGENTA + Style.BRIGHT + "\n  🤖 [ReAct Agent]: Multi-step research pipeline starting.")
    print(SEP)

    gathered = {}   # {"wikipedia": str|None, "web": str|None}

    # ── STEP 1: PLAN ─────────────────────────────────────────────────────
    print(Fore.CYAN + "  [1/4] Plan  : Generating optimised sub-queries...")
    wiki_query, web_query = _plan_subqueries(processed_input, config)
    print(Fore.CYAN + f"         Wiki : \"{wiki_query}\"")
    print(Fore.CYAN + f"         Web  : \"{web_query}\"")

    # ── STEP 2: ACT — WIKIPEDIA ──────────────────────────────────────────
    print(Fore.CYAN + "  [2/4] Act   : Wikipedia — fetching encyclopedic background...")
    try:
        wiki_result = _wiki.summary(wiki_query, sentences=4, auto_suggest=True)
        gathered["wikipedia"] = wiki_result
        print(Fore.GREEN + f"         OK   : {len(wiki_result)} chars from Wikipedia.")
    except Exception as e:
        gathered["wikipedia"] = None
        print(Fore.YELLOW + f"         Warn : Wikipedia failed — {str(e)[:55]}")

    # ── STEP 3: ACT — WEB SCRAPE ─────────────────────────────────────────
    print(Fore.CYAN + "  [3/4] Act   : Web — scraping live network data...")
    web_result = search_google_scrape(web_query)
    if web_result:
        gathered["web"] = web_result
        print(Fore.GREEN + f"         OK   : {len(web_result)} chars from web scraper.")
    else:
        gathered["web"] = None
        print(Fore.YELLOW + "         Warn : Web scraper returned no results.")

    # ── OBSERVE: Combine what we have ────────────────────────────────────
    sources_used = [k for k, v in gathered.items() if v]
    if not sources_used:
        print(Fore.RED + "         Fail : All data sources offline. Falling back to local model...")
        reply, _ = call_ollama_fn(user_input)
        print(SEP)
        return reply or "❌ ReAct pipeline failed — Wikipedia, web scraper, and local model all offline."

    combined = ""
    if gathered.get("wikipedia"):
        combined += f"[Wikipedia Background]\n{gathered['wikipedia']}\n\n"
    if gathered.get("web"):
        combined += f"[Live Web Data]\n{gathered['web']}\n\n"

    # ── STEP 4: SYNTHESIZE ────────────────────────────────────────────────
    print(Fore.CYAN + f"  [4/4] Synth : Combining {' + '.join(s.capitalize() for s in sources_used)}...")

    synthesis_prompt = (
        f"You are Jarvis, a precise terminal assistant created by {config.DEVELOPER_ALIAS}. "
        f"Using ONLY the research data below, write a clear and well-structured answer to the user query. "
        f"Use numbered points or headings where appropriate. Be concise but complete.\n\n"
        f"=== RESEARCH DATA ===\n{combined}"
        f"=== USER QUERY ===\n{user_input}\n\n"
        f"=== YOUR ANSWER ==="
    )

    synthesizer = None

    # Try Gemini first (superior synthesis quality)
    if config.API_KEY and "YOUR_GEMINI" not in config.API_KEY:
        try:
            payload = {"contents": [{"role": "user", "parts": [{"text": synthesis_prompt}]}]}
            res     = gemini_safe_request(payload)
            if res.status_code == 200:
                reply      = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                synthesizer = "Gemini"
            else:
                print(Fore.YELLOW + f"         Warn : Gemini synthesis HTTP {res.status_code}. Trying Ollama...")
        except Exception as e:
            print(Fore.YELLOW + f"         Warn : Gemini failed ({str(e)[:45]}). Trying Ollama...")

    # Fallback: Ollama synthesis
    if not synthesizer:
        reply, err = call_ollama_fn(synthesis_prompt)
        if reply:
            synthesizer = "Ollama"
        else:
            # Last resort: return raw combined data
            print(Fore.YELLOW + "         Warn : Synthesis model offline. Serving raw research data.")
            print(SEP)
            return f"Research results for '{user_input}':\n\n{combined.strip()}"

    print(Fore.GREEN + f"         OK   : Synthesis complete via {synthesizer}.")
    print(SEP)
    print(Fore.MAGENTA + f"  Sources used : {' + '.join(s.capitalize() for s in sources_used)} -> {synthesizer}")
    print(Fore.WHITE + "")
    return reply
