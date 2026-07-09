"""
routing/knowledge_engine.py
============================
Collects knowledge from multiple sources BEFORE asking any AI model.

Sources (selected based on intent type):
  • Web search   — live DuckDuckGo scrape  (WEB_SEARCH, UNKNOWN)
  • Wikipedia    — encyclopedic summary     (WIKIPEDIA, REASONING, WEB_SEARCH)
  • Chat history — recent conversation      (CHAT, MEMORY, CODING, REASONING)

The engine returns a context dict consumed by ai_router.py and ProviderManager.

Context dict keys:
    web_data    : str | missing   — raw web-scrape text
    wiki_data   : str | missing   — Wikipedia summary text
    chat_ctx    : str | missing   — formatted recent chat turns
    has_context : bool            — True if web_data or wiki_data present
"""

from __future__ import annotations

from typing import Callable

from .intent_detector import IntentType

# Wikipedia is optional (not available on every install)
try:
    import wikipedia as _wikipedia
    _WIKI_OK = True
except ImportError:
    _WIKI_OK = False

# Intents that need live web data
_WEB_INTENTS  = frozenset([IntentType.WEB_SEARCH, IntentType.UNKNOWN])

# Intents that benefit from Wikipedia background
_WIKI_INTENTS = frozenset([
    IntentType.WEB_SEARCH,
    IntentType.WIKIPEDIA,
    IntentType.UNKNOWN,
    IntentType.REASONING,
])

# Intents that benefit from recent chat history
_HIST_INTENTS = frozenset([
    IntentType.CHAT,
    IntentType.MEMORY,
    IntentType.CODING,
    IntentType.REASONING,
])


class KnowledgeEngine:
    """
    Multi-source knowledge collector.

    Usage (called once per user turn, after intent classification):

        ctx = KnowledgeEngine.collect(
            query        = processed_input,
            intent       = IntentType.WEB_SEARCH,
            config       = config,
            chat_log     = config.chat_log,
            web_scraper  = commands.search_google_scrape,
        )

        # ctx["web_data"]   → scraped text (may be absent)
        # ctx["wiki_data"]  → Wikipedia text (may be absent)
        # ctx["chat_ctx"]   → recent turns formatted as "You: ...\nJarvis: ..."
        # ctx["has_context"]→ True if web_data or wiki_data collected
    """

    @staticmethod
    def collect(
        query: str,
        intent: IntentType,
        config,
        chat_log: list | None = None,
        web_scraper: Callable[[str], str | None] | None = None,
    ) -> dict:
        """
        Parameters
        ----------
        query       : processed (lowercased) user query
        intent      : classified intent from IntentDetector
        config      : jarvis config module
        chat_log    : session log [{role, text, timestamp}, ...]
        web_scraper : callable(query) → str | None  (commands.search_google_scrape)
        """
        ctx: dict = {}

        # ── Web search ─────────────────────────────────────────────────────
        if intent in _WEB_INTENTS and web_scraper is not None:
            print("🌐 [Knowledge Engine]: Fetching live web data...")
            try:
                web_text = web_scraper(query)
                if web_text and web_text.strip():
                    ctx["web_data"] = web_text.strip()
                    print(f"✅ [Knowledge Engine]: Web — {len(ctx['web_data'])} chars captured.")
                else:
                    print("⚠️  [Knowledge Engine]: Web scraper returned empty result.")
            except Exception as ex:
                print(f"⚠️  [Knowledge Engine]: Web scraper error — {str(ex)[:60]}")

        # ── Wikipedia ──────────────────────────────────────────────────────
        if intent in _WIKI_INTENTS and _WIKI_OK:
            print("📖 [Knowledge Engine]: Fetching Wikipedia data...")
            try:
                wiki_text = _wikipedia.summary(query, sentences=3, auto_suggest=True)
                ctx["wiki_data"] = wiki_text.strip()
                print(f"✅ [Knowledge Engine]: Wikipedia — {len(ctx['wiki_data'])} chars captured.")
            except Exception as ex:
                # DisambiguationError, PageError, etc. are common — always silent
                print(f"⚠️  [Knowledge Engine]: Wikipedia — {str(ex)[:60]}")

        # ── Chat history context ───────────────────────────────────────────
        if intent in _HIST_INTENTS and chat_log:
            max_hist = getattr(config, "MAX_CHAT_HISTORY", 6)
            recent   = chat_log[-max_hist:]
            lines    = []
            for entry in recent:
                role = "You" if entry.get("role") == "user" else "Jarvis"
                text = entry.get("text", "").strip()
                if text:
                    lines.append(f"{role}: {text}")
            if lines:
                ctx["chat_ctx"] = "\n".join(lines)

        # ── Summary flag ───────────────────────────────────────────────────
        ctx["has_context"] = bool(ctx.get("web_data") or ctx.get("wiki_data"))

        return ctx
