""" 
engine/knowledge_planner.py
============================
Dynamic knowledge source planner — v2.

Two key decisions made here:

1. FRESHNESS DETECTION
   Does this query need up-to-date real-world data?
   YES → Web first, then Wikipedia (fallback)
   NO  → Wikipedia first (encyclopedic, stable), Web only if confidence low

2. CONFIDENCE-BASED FALLBACK
   If the first source gives a low-confidence answer (< threshold),
   automatically collect from additional sources and merge.

Query signals that trigger "need latest" mode
--------------------------------------------
  who is the / current / latest / today / 2024/2025/2026
  price / rate / news / CM / PM / CEO / election / result
  vs.
  encyclopedic: what is / define / explain / history / how does

Usage
-----
    from engine.knowledge_planner import KnowledgePlan

    # Ordered list of sources for this query + intent
    sources = KnowledgePlan.plan(intent="WIKIPEDIA", query="who is cm of wb")
    # returns [WebSearchSource, WikipediaSource]  ← web FIRST for latest queries

    # Multi-source fetch with confidence fallback
    ctx = KnowledgePlan.collect_with_fallback(
        query="who is cm of wb",
        intent="WIKIPEDIA",
        web_scraper=fn,
        config=config,
    )
"""

from __future__ import annotations

from .source_registry import SourceRegistry, KnowledgeSource


# ─────────────────────────────────────────────────────────────────────────────
# Freshness signals — queries containing these NEED live web data first
# ─────────────────────────────────────────────────────────────────────────────
_LATEST_SIGNALS = frozenset([
    # Explicit recency
    "current", "latest", "today", "now", "recent", "live", "real-time",
    "right now", "at present", "currently", "as of",
    # Years (treat as dynamic)
    "2024", "2025", "2026", "2027",
    # Political roles that change (government/corporate)
    "who is the", "chief minister", "prime minister", "president",
    "cm of", "pm of", "ceo of", "coo of", "chairman", "governor",
    "head of", "leader of", "director of", "minister of",
    "mp from", "mla from",
    # Financial / market data
    "price", "rate", "stock", "crypto", "bitcoin", "dollar",
    "exchange rate", "market", "sensex", "nifty",
    # News / events
    "news", "update", "happen", "result", "score", "winner",
    "election", "match", "weather", "forecast",
    # Sports
    "ipl", "world cup", "champion", "won", "beat",
])

# Encyclopedic signals — these DON'T need fresh web data (Wikipedia is better)
_ENCYCLOPEDIC_SIGNALS = frozenset([
    "what is", "define", "definition", "explain", "meaning",
    "history of", "origin of", "how does", "how do", "how did",
    "who was", "when did", "where is located", "biography",
    "concept", "theory", "formula", "equation",
])


class KnowledgePlan:
    """
    Static planner — call KnowledgePlan.plan() or collect_with_fallback().
    """

    @staticmethod
    def needs_latest(query: str) -> bool:
        """
        Return True when the query asks for up-to-date real-world information.
        Encyclopedic signals override latest signals when both are present.
        """
        q = query.lower()
        # Encyclopedic takes priority ("what is the current theory" → wiki is fine)
        if any(sig in q for sig in _ENCYCLOPEDIC_SIGNALS):
            # But if there's also a strong recency word, still prefer web
            strong_recency = any(s in q for s in [
                "current", "latest", "today", "2026", "2025", "2024",
                "who is the", "price", "rate", "news", "election result",
            ])
            return strong_recency
        return any(sig in q for sig in _LATEST_SIGNALS)

    @staticmethod
    def plan(
        intent: str,
        query: str = "",
    ) -> list[KnowledgeSource]:
        """
        Return ordered knowledge sources for *intent* and *query*.

        If the query needs latest data → Web comes BEFORE Wikipedia.
        Otherwise → Wikipedia comes first (stable, reliable).
        """
        sources = SourceRegistry.get_sources_for(intent, available_only=True)

        if not sources:
            # For WIKIPEDIA intent, also allow web as fallback
            sources = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)

        if not KnowledgePlan.needs_latest(query):
            return sources   # default registry order (Wikipedia priority=7 > Web)

        # Latest mode: sort so web (priority=8) beats wikipedia (priority=7)
        # Both are already in the registry — just let priority do the work
        # But we also want to ENSURE web is tried even for WIKIPEDIA intent
        web_sources  = [s for s in sources if s.name == "web"]
        wiki_sources = [s for s in sources if s.name == "wikipedia"]
        hist_sources = [s for s in sources if s.name == "chat_history"]
        other        = [s for s in sources if s.name not in ("web", "wikipedia", "chat_history")]

        # Latest order: Web → Wikipedia → others → chat_history
        return web_sources + wiki_sources + other + hist_sources

    @staticmethod
    def collect_with_fallback(
        query: str,
        intent: str,
        web_scraper,
        config,
        chat_log: list | None = None,
        confidence_threshold: float = 0.55,
        max_sources: int = 3,
    ) -> dict:
        """
        Collect knowledge with automatic confidence-based fallback.

        Flow
        ----
        1. Get ordered sources from plan()
        2. Fetch from source[0]
        3. Score confidence of the result
        4. If score < threshold → fetch source[1], source[2], ...
        5. Merge ALL collected data into one context dict
        6. Return merged context (more data = better AI synthesis)

        Returns
        -------
        dict with keys: web_data, wiki_data, chat_ctx, has_context,
                        sources_used (list of source names), needs_more_sources (bool)
        """
        from engine.confidence_engine import ConfidenceEngine
        import wikipedia as _wiki_mod

        ctx: dict = {
            "web_data":         None,
            "wiki_data":        None,
            "chat_ctx":         None,
            "has_context":      False,
            "sources_used":     [],
            "needs_more_sources": False,
        }

        # ── Inject runtime dependencies into registry ─────────────────────────
        from engine.source_registry import configure_web_scraper, configure_chat_log
        if web_scraper:
            configure_web_scraper(web_scraper)
        if chat_log is not None:
            max_turns = getattr(config, "MAX_CHAT_HISTORY", 6)
            configure_chat_log(chat_log, max_turns)

        # ── Get source order for this query ───────────────────────────────────
        # For WIKIPEDIA intent, explicitly add web as potential source
        all_source_names = {s.name for s in SourceRegistry.all_sources()}
        sources = KnowledgePlan.plan(intent, query)

        # For WIKIPEDIA intent, always include web as a potential fallback
        if intent in ("WIKIPEDIA", "REASONING") and "web" not in [s.name for s in sources]:
            web_srcs = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)
            if KnowledgePlan.needs_latest(query):
                sources = web_srcs + sources   # web FIRST
            else:
                sources = sources + web_srcs   # web as fallback

        current_confidence = 0.0
        fetched = 0

        for source in sources:
            if fetched >= max_sources:
                break

            # Skip if we already have high confidence and don't need more data
            if current_confidence >= 0.75 and fetched >= 1:
                break

            try:
                if source.name == "web":
                    if web_scraper is None:
                        continue
                    print("🌐 [Knowledge Engine]: Fetching live web data...")
                    data = web_scraper(query)
                    if data and data.strip():
                        ctx["web_data"] = data.strip()
                        ctx["sources_used"].append("web")
                        fetched += 1
                        print(f"✅ [Knowledge Engine]: Web — {len(data)} chars captured.")
                        # Score this result
                        score = ConfidenceEngine.score(
                            answer=data, sources={"web": data[:200]}, source_name="web"
                        )
                        current_confidence = max(current_confidence, score)
                        print(f"🎯 [Planner]: Web confidence = {score:.2f}")
                    else:
                        print("⚠️  [Knowledge Engine]: Web scraper returned empty.")

                elif source.name == "wikipedia":
                    print("📖 [Knowledge Engine]: Fetching Wikipedia data...")
                    try:
                        wiki_text = _wiki_mod.summary(query, sentences=4, auto_suggest=True)
                        if wiki_text and wiki_text.strip():
                            ctx["wiki_data"] = wiki_text.strip()
                            ctx["sources_used"].append("wikipedia")
                            fetched += 1
                            print(f"✅ [Knowledge Engine]: Wikipedia — {len(wiki_text)} chars captured.")
                            # Score this result
                            score = ConfidenceEngine.score(
                                answer=wiki_text, sources={"wikipedia": wiki_text[:200]},
                                source_name="wikipedia"
                            )
                            if current_confidence < score:
                                current_confidence = score
                            print(f"🎯 [Planner]: Wikipedia confidence = {score:.2f}")
                            # If confidence is LOW, flag that we need more sources
                            if score < confidence_threshold:
                                ctx["needs_more_sources"] = True
                                print(f"⚠️  [Planner]: Confidence {score:.2f} < {confidence_threshold} — fetching more sources...")
                    except Exception as wiki_ex:
                        print(f"⚠️  [Knowledge Engine]: Wikipedia — {str(wiki_ex)[:80]}")

                elif source.name == "chat_history":
                    if chat_log:
                        max_h = getattr(config, "MAX_CHAT_HISTORY", 6)
                        recent = chat_log[-max_h:]
                        lines  = []
                        for entry in recent:
                            role = "You" if entry.get("role") == "user" else "Jarvis"
                            text = entry.get("text", "").strip()
                            if text:
                                lines.append(f"{role}: {text}")
                        if lines:
                            ctx["chat_ctx"] = "\n".join(lines)
                            ctx["sources_used"].append("chat_history")

            except Exception as ex:
                print(f"⚠️  [Planner]: Source '{source.name}' error — {str(ex)[:60]}")

        ctx["has_context"] = bool(ctx.get("web_data") or ctx.get("wiki_data"))

        if ctx["sources_used"]:
            merged_label = " + ".join(ctx["sources_used"])
            print(f"🔗 [Planner]: Merged sources → {merged_label} (confidence={current_confidence:.2f})")

        return ctx


