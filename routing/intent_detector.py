"""
routing/intent_detector.py
===========================
Hybrid intent classifier for JARVIS.

Classification tiers (fastest → slowest):
  Tier 1 — Single-word / short conversational tokens  → CHAT instantly
  Tier 2 — Rule-based keyword matching               → no LLM, <1 ms
  Tier 3 — Ollama LLM classification                  → ~5 s, ambiguous cases

Replaces the old get_tool_routing_decision() + is_react_query() combo
with a richer, unified 10-category taxonomy.

Intent categories
-----------------
LOCAL_COMMAND  battery, weather, time, music, tasks, etc.
CHAT           casual conversation, greetings, opinions
CODING         write/debug/implement code
REASONING      analyze, compare, calculate, research & summarize
VISION         image analysis, visual description
WEB_SEARCH     live/current/real-time data needs
WIKIPEDIA      encyclopedic facts, definitions, biographies
MEMORY         questions about earlier in the conversation
FILE_SEARCH    read/open/analyze local files
UNKNOWN        unclassified → routed to WEB_SEARCH pipeline
"""

from __future__ import annotations

from enum import Enum

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Intent taxonomy
# ─────────────────────────────────────────────────────────────────────────────

class IntentType(str, Enum):
    LOCAL_COMMAND = "LOCAL_COMMAND"
    CHAT          = "CHAT"
    CODING        = "CODING"
    REASONING     = "REASONING"
    VISION        = "VISION"
    WEB_SEARCH    = "WEB_SEARCH"
    WIKIPEDIA     = "WIKIPEDIA"
    MEMORY        = "MEMORY"
    FILE_SEARCH   = "FILE_SEARCH"
    UNKNOWN       = "UNKNOWN"

    def to_cache_key(self) -> str:
        """
        Map this intent to the 'decision' key expected by the knowledge-cache
        write logic in jarvis.py.

        "web"          → cache with source=web/web+gemini
        "react"        → cache with source=react, confidence=high
        "conversation" → do NOT cache
        """
        _MAP = {
            IntentType.WEB_SEARCH:    "web",
            IntentType.WIKIPEDIA:     "web",
            IntentType.UNKNOWN:       "web",
            IntentType.REASONING:     "react",   # multi-source, high confidence
            IntentType.CHAT:          "conversation",
            IntentType.CODING:        "conversation",
            IntentType.VISION:        "conversation",
            IntentType.MEMORY:        "conversation",
            IntentType.LOCAL_COMMAND: "conversation",
            IntentType.FILE_SEARCH:   "conversation",
        }
        return _MAP.get(self, "conversation")


# ─────────────────────────────────────────────────────────────────────────────
# Keyword sets (Tier 2 rule engine)
# ─────────────────────────────────────────────────────────────────────────────

# Note: these are checked as substrings — order of checks matters (more specific first).

_LOCAL_PREFIXES = (
    "add task", "show task", "remove task",
    "play youtube", "play music", "play song", "play random",
    "list music", "stop music", "stop song", "stop youtube",
    "open youtube", "open google",
    "read file", "read chat", "read log",
    "forget ",
)

_LOCAL_EXACT = frozenset([
    "battery", "battery status", "charge",
    "weather", "temperature", "forecast",
    "location", "gps",
    "calendar", "time", "date",
    "stop", "help", "clear", "cls", "clear screen",
])

_CODING_PHRASES = frozenset([
    "write code", "code for", "python code", "javascript code",
    "typescript code", "write a script", "write a function",
    "write a class", "write a program", "write me a",
    "debug this", "fix this code", "fix the bug", "fix the error",
    "implement ", "algorithm for", "function that", "class that",
    "program to", "script to", "code to", "code that",
    "syntax error", "runtime error", "traceback",
    "html page", "css style", "sql query", "regex for",
    "how to code", "how to program", "how to implement",
    "give me the code", "show me the code",
    # Extended — catches 'write a python function', 'python function to'
    "python function", "python script", "python program",
    "javascript function", "java function", "a function to",
    "a program to", "a script to",
])

_REASONING_PHRASES = frozenset([
    "analyze ", "analyse ", "compare ", "comparison between",
    "optimize ", "optimise ", "evaluate ", "assess ",
    "pros and cons", "advantages and disadvantages",
    "prove ", "logical ", "calculate ", "solve ",
    "step by step", "think through", "reason about",
    "which is better", "which is best", "trade off", "tradeoff",
    "should i ", "is it worth",
    # Old ReAct trigger words — absorbed here
    "research ", "summarize ", "summarise ", "summary of",
    "comprehensive ", "in detail", "thoroughly",
    "explain everything", "full explanation", "complete guide",
    "deep dive", "break down", "breakdown",
    "all about", "tell me everything", "differences between",
    "pros and cons of", "teach me",
])

_VISION_PHRASES = frozenset([
    "describe this image", "analyze this image", "analyse this image",
    "what is in this image", "what is in the image",
    "look at this", "what do you see", "what's in the picture",
    "image analysis", "read this image", "text in this image",
    "describe the photo", "describe the picture",
])

_WEB_PHRASES = frozenset([
    "latest ", "recent ", "breaking news", "today's news",
    "current ", "right now", "happening now",
    " update ", " updates ",
    "trending", "live score", "stock price", "crypto price",
    "who won", "match result", "release date",
    "new version", "new update", "just launched",
])

# Year patterns for detecting current-events queries
_YEAR_RE_STRS = ("2024", "2025", "2026", "2027")

_WIKI_PHRASES = frozenset([
    "who is ", "who was ", "what is ", "what was ", "what are ",
    "definition of", "meaning of", "what does  mean",
    "history of ", "origin of ", "biography of",
    "when was ", "when did ", "where is ", "where was ",
    "founded by", "invented by", "discovered by",
    "capital of ", "population of ", "president of ",
    "prime minister of ", "how does  work", "how does it work",
    "explain what is", "tell me about ",
])

_MEMORY_PHRASES = frozenset([
    "what did i ask", "what did you say", "earlier you said",
    "you told me", "i asked you", "remember when",
    "last time you", "previously you", "before you said",
    "from our conversation", "you mentioned",
    "what was my last question",
])

_FILE_PHRASES = frozenset([
    "read file", "open file", "file content",
    "show file", "read the file", "what is in the file",
    "what is in the", "what's in the",
    "contents of the file", "inside the file", "from the file",
])

# Very short conversational words — always CHAT (no LLM needed)
_CHAT_TOKENS = frozenset([
    "ok", "okay", "yes", "no", "nope", "yep", "sure", "thanks",
    "thank", "bye", "goodbye", "hello", "hi", "hey", "alright",
    "great", "good", "nice", "cool", "fine", "got it", "understood",
    "please", "sorry", "hmm", "hm", "right", "indeed", "exactly",
    "wow", "amazing", "interesting", "awesome", "ok got it",
    "perfect", "noted", "copy that", "roger",
])

# Question starters that suggest WEB_SEARCH when no other rule fires
_QUESTION_STARTERS = frozenset([
    "who", "what", "when", "where", "why", "how",
    "which", "is", "are", "was", "were", "can", "could",
    "does", "did", "will", "would", "should",
])


# ─────────────────────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────────────────────

class IntentDetector:
    """
    Classify a user query into an IntentType.

    The public interface is a single static method:

        intent = IntentDetector.detect(processed_input, config)

    *processed_input* should be the lowercased, stripped user string
    (same as what jarvis.py already computes before calling handle_command).
    """

    @staticmethod
    def detect(
        query: str,
        config=None,
        use_llm: bool = True,
    ) -> IntentType:
        """
        Parameters
        ----------
        query    : lowercased user input
        config   : jarvis config module — needed for Tier 3 Ollama call
        use_llm  : set False to skip the Ollama call (useful in unit tests)
        """
        q = query.lower().strip()

        # ── Tier 1: Single-token conversational bypass ────────────────────────
        # NOTE: we check LOCAL_EXACT FIRST before the length bypass,
        # so single-word commands like 'time', 'stop', 'date' are not swallowed.
        bare = q.strip("'\".,!?;:")
        if bare in _LOCAL_EXACT:
            return IntentType.LOCAL_COMMAND
        if bare in _CHAT_TOKENS:
            return IntentType.CHAT
        if len(q.split()) <= 1 and len(q) <= 4:
            return IntentType.CHAT

        # ── Tier 2a: Local command — prefix match ─────────────────────────────
        for prefix in _LOCAL_PREFIXES:
            if q.startswith(prefix):
                return IntentType.LOCAL_COMMAND

        # ── Tier 2b: Local command — exact / keyword match ───────────────────
        if q in _LOCAL_EXACT or any(kw == q for kw in _LOCAL_EXACT):
            return IntentType.LOCAL_COMMAND
        # single exact keyword anywhere in short queries
        if len(q.split()) <= 3 and any(kw in q.split() for kw in _LOCAL_EXACT):
            return IntentType.LOCAL_COMMAND

        # ── Tier 2c: File search ──────────────────────────────────────────────
        if any(ph in q for ph in _FILE_PHRASES):
            return IntentType.FILE_SEARCH

        # ── Tier 2d: Memory / follow-up ──────────────────────────────────────
        if any(ph in q for ph in _MEMORY_PHRASES):
            return IntentType.MEMORY

        # ── Tier 2e: Vision ───────────────────────────────────────────────────
        if any(ph in q for ph in _VISION_PHRASES):
            return IntentType.VISION

        # ── Tier 2f: Reasoning / complex research (≥4 words) ─────────────────
        # Checked BEFORE coding so 'optimize' beats 'implement'
        if len(q.split()) >= 4 and any(ph in q for ph in _REASONING_PHRASES):
            return IntentType.REASONING

        # ── Tier 2g: Coding ───────────────────────────────────────────────────
        if any(ph in q for ph in _CODING_PHRASES):
            return IntentType.CODING

        # ── Tier 2h: Live web search ──────────────────────────────────────────
        if any(ph in q for ph in _WEB_PHRASES):
            return IntentType.WEB_SEARCH
        # Year-based detection (handles queries starting with a year)
        if any(yr in q for yr in _YEAR_RE_STRS):
            return IntentType.WEB_SEARCH

        # ── Tier 2i: Wikipedia encyclopedic lookup ───────────────────────────
        if any(ph in q for ph in _WIKI_PHRASES):
            return IntentType.WIKIPEDIA

        # ── Tier 3: Ollama LLM for ambiguous queries ──────────────────────────
        if config is not None and use_llm:
            llm_intent = IntentDetector._ollama_classify(q, config)
            if llm_intent is not None:
                return llm_intent

        # ── Default heuristic: question format → WEB_SEARCH ──────────────────
        words = q.split()
        if len(words) >= 3 and words[0] in _QUESTION_STARTERS:
            return IntentType.WEB_SEARCH

        # ── Ultimate fallback ─────────────────────────────────────────────────
        return IntentType.CHAT

    # ─────────────────────────────────────────────────────────────────────────
    # Tier 3 — Ollama LLM classifier
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ollama_classify(query: str, config) -> IntentType | None:
        """
        Ask the local Ollama model to classify *query*.
        Returns an IntentType on success, or None if Ollama is unavailable
        (in which case the caller falls through to the default heuristic).
        """
        prompt = (
            "You are a query classifier for an AI assistant. "
            "Classify the query below into exactly ONE category. "
            "Output ONLY the category name — nothing else.\n\n"
            "Categories:\n"
            "  CHAT        — greetings, casual talk, opinions\n"
            "  CODING      — write/debug/implement code, algorithms\n"
            "  REASONING   — analyze, compare, calculate, research topics\n"
            "  WEB_SEARCH  — latest news, real-time data, prices\n"
            "  WIKIPEDIA   — historical facts, definitions, biographies\n"
            "  VISION      — image or picture analysis\n"
            "  MEMORY      — questions about this conversation\n"
            "  FILE_SEARCH — read or analyze local files\n\n"
            f"Query: {query}"
        )
        try:
            res = requests.post(
                config.OLLAMA_URL,
                json={
                    "model":    config.LOCAL_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"temperature": 0.0, "num_ctx": 512},
                },
                timeout=5,
            )
            raw = res.json()["message"]["content"].upper().strip()
            # Extract first matching category word from the response
            _CATS = [
                "CODING", "REASONING", "WEB_SEARCH", "WIKIPEDIA",
                "VISION", "MEMORY", "FILE_SEARCH", "CHAT",
            ]
            for cat in _CATS:
                if cat in raw:
                    return IntentType[cat]
        except Exception:
            pass  # Ollama offline or timed out — caller falls through
        return None
