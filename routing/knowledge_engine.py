"""
routing/knowledge_engine.py
============================
Collects knowledge from multiple sources BEFORE asking any AI model.

v7.2: Fully delegates to engine.knowledge_planner.KnowledgePlan which:
  1. Always fetches Web FIRST (highest freshness score = 0.76)
  2. Then Wikipedia for verification/background (score = 0.685)
  3. Automatically fetches more sources when confidence is low (< 0.55)
  4. Merges all sources before returning context

Source priority (driven by compute_score, NOT hardcoded):
  ALL queries → Web (0.76) → Wikipedia (0.685) → Chat History
  
  Source score = freshness*0.4 + authority*0.3 + reliability*0.3
    Web:       1.0*0.4 + 0.5*0.3 + 0.7*0.3 = 0.76   (highest)
    Wikipedia: 0.4*0.4 + 0.9*0.3 + 0.85*0.3 = 0.685 (second)

Context dict keys:
    web_data    : str | None   — raw web-scrape text
    wiki_data   : str | None   — Wikipedia summary text
    chat_ctx    : str | None   — formatted recent chat turns
    has_context : bool         — True if web_data or wiki_data present
    sources_used: list[str]    — e.g. ["web", "wikipedia"]
"""

from __future__ import annotations

from typing import Callable

from .intent_detector import IntentType

# ── Engine layer (dynamic planner with freshness + confidence fallback) ────────
try:
    from engine.knowledge_planner import KnowledgePlan
    _PLANNER_AVAILABLE = True
except ImportError:
    _PLANNER_AVAILABLE = False

# Wikipedia direct import (used in legacy mode)
try:
    import wikipedia as _wikipedia
    _WIKI_OK = True
except ImportError:
    _WIKI_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# Legacy frozensets (only used when engine/ is not importable)
# ─────────────────────────────────────────────────────────────────────────────
_WEB_INTENTS  = frozenset([IntentType.FACT_QUERY, IntentType.UNKNOWN])
_WIKI_INTENTS = frozenset([
    IntentType.FACT_QUERY, IntentType.UNKNOWN, IntentType.REASONING_REQUEST,
])
_HIST_INTENTS = frozenset([
    IntentType.CONVERSATIONAL, IntentType.MEMORY_QUERY,
    IntentType.CODING_REQUEST, IntentType.REASONING_REQUEST,
])


class KnowledgeEngine:
    """
    Multi-source knowledge collector.

    v7.2 — delegates to KnowledgePlan.collect_with_fallback():
      - Web always first (freshness score 0.76 > Wikipedia 0.685)
      - Confidence-based fallback: low score → fetch more sources
      - Merges all sources into one context dict

    Usage (called once per user turn, after intent classification):

        ctx = KnowledgeEngine.collect(
            query        = processed_input,
            intent       = IntentType.WIKIPEDIA,
            config       = config,
            chat_log     = config.chat_log,
            web_scraper  = commands.search_google_scrape,
        )

        ctx["web_data"]    → scraped text (may be None)
        ctx["wiki_data"]   → Wikipedia text (may be None)
        ctx["chat_ctx"]    → recent turns formatted as "You: ...\\nJarvis: ..."
        ctx["has_context"] → True if web_data or wiki_data collected
        ctx["sources_used"]→ ["web", "wikipedia"] (for logging)
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
        query       : processed (normalized) user query
        intent      : classified intent from IntentDetector
        config      : jarvis config module
        chat_log    : session log [{role, text, timestamp}, ...]
        web_scraper : callable(query) → str | None
        """

        # ── v8: Execute dynamic planner with freshness + confidence fallback ────
        if _PLANNER_AVAILABLE:
            from engine.knowledge_planner import KnowledgePlanner
            from engine.source_registry import configure_web_scraper, configure_chat_log

            # Configure dynamic sources
            if web_scraper:
                configure_web_scraper(web_scraper)
            if chat_log:
                configure_chat_log(chat_log)

            k_plan = KnowledgePlanner.plan(query, intent)
            ctx = {"has_context": False, "sources_used": []}

            for source in k_plan.sources:
                if not source.is_available():
                    continue
                
                print(f"🌐 [Knowledge Engine]: Fetching from {source.name}...")
                try:
                    data = source.fetch(query)
                    if data:
                        if source.name == "web":
                            ctx["web_data"] = data
                        elif source.name == "wikipedia":
                            ctx["wiki_data"] = data
                        elif source.name == "chat_history":
                            ctx["chat_ctx"] = data
                        
                        ctx["sources_used"].append(source.name)
                        ctx["has_context"] = True
                        print(f"✅ [Knowledge Engine]: {source.name.capitalize()} — {len(data)} chars captured.")
                    else:
                        print(f"⚠️  [Knowledge Engine]: {source.name.capitalize()} returned empty result.")
                except Exception as ex:
                    print(f"⚠️  [Knowledge Engine]: {source.name.capitalize()} error — {str(ex)[:60]}")
            
            return ctx

        # ── Legacy fallback (when engine/ is not available) ──────────────────
        return KnowledgeEngine._legacy_collect(
            query=query, intent=intent, config=config,
            chat_log=chat_log, web_scraper=web_scraper,
        )

    @staticmethod
    def _legacy_collect(
        query: str,
        intent: IntentType,
        config,
        chat_log: list | None = None,
        web_scraper: Callable[[str], str | None] | None = None,
    ) -> dict:
        """Legacy fixed-order collection (used when engine/ unavailable)."""
        ctx: dict = {}

        # Web search
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

        # Wikipedia
        if intent in _WIKI_INTENTS and _WIKI_OK:
            print("📖 [Knowledge Engine]: Fetching Wikipedia data...")
            try:
                wiki_text = _wikipedia.summary(query, sentences=3, auto_suggest=True)
                ctx["wiki_data"] = wiki_text.strip()
                print(f"✅ [Knowledge Engine]: Wikipedia — {len(ctx['wiki_data'])} chars captured.")
            except Exception as ex:
                print(f"⚠️  [Knowledge Engine]: Wikipedia — {str(ex)[:60]}")

        # Chat history
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

        ctx["has_context"]  = bool(ctx.get("web_data") or ctx.get("wiki_data"))
        ctx["sources_used"] = []
        return ctx
