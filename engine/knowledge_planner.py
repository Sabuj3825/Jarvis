"""
engine/knowledge_planner.py
============================
Dynamic knowledge source planner — v3.

CORE PRINCIPLE: NO hardcoded source ordering. NO "if source.name == web".

Source ordering is driven entirely by metadata scores:
    score = freshness * 0.4 + authority * 0.3 + reliability * 0.3

With current metadata:
    Web         → score = 1.0*0.4 + 0.5*0.3 + 0.7*0.3 = 0.76  → ALWAYS FIRST
    Wikipedia   → score = 0.4*0.4 + 0.9*0.3 + 0.85*0.3 = 0.685 → SECOND
    ChatHistory → score = 0.8*0.4 + 0.6*0.3 + 0.9*0.3 = 0.77   → (only for CHAT/MEMORY)

The planner:
  1. Queries SourceRegistry for sources matching the intent
  2. Registry returns sources sorted by compute_score() (highest first)
  3. Fetches from each source in order using source.fetch(query) — NOT hardcoded
  4. Scores each source's data using ConfidenceEngine
  5. If confidence < threshold after first source → continues to next source
  6. Merges ALL collected data into one context dict for the AI

Usage
-----
    from engine.knowledge_planner import KnowledgePlan

    ctx = KnowledgePlan.collect_with_fallback(
        query="who is cm of wb",
        intent="WIKIPEDIA",
        web_scraper=commands.search_google_scrape,
        config=config,
    )
"""

from __future__ import annotations

from colorama import Fore

from .source_registry import SourceRegistry, KnowledgeSource


class KnowledgePlan:
    """
    Stateless planner — call KnowledgePlan.collect_with_fallback() to get
    a merged context dict from all relevant knowledge sources.
    """

    @staticmethod
    def plan(
        intent: str,
        query: str = "",
    ) -> list[KnowledgeSource]:
        """
        Return ordered knowledge sources for *intent*.

        Ordering is determined by each source's compute_score()
        (freshness*0.4 + authority*0.3 + reliability*0.3).
        NO hardcoded ordering — the source with the highest score comes first.

        With default metadata:
            Web (0.76) → Wikipedia (0.685) → ChatHistory (0.77, but only for CHAT/MEMORY)
        """
        sources = SourceRegistry.get_sources_for(intent, available_only=True)

        if not sources:
            # Fallback: try WEB_SEARCH intent sources for any unmatched intent
            sources = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)

        return sources  # already sorted by compute_score() in the registry

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
        Collect knowledge from multiple sources with confidence-based fallback.

        Flow
        ----
        1. Get sources sorted by score from plan()
        2. Ensure web + wikipedia are available for knowledge-bearing intents
        3. Fetch from source[0] using source.fetch(query)
        4. Score the fetched data
        5. If score < threshold → fetch source[1], source[2]...
        6. Merge ALL collected data into one context dict
        7. Return merged context

        KEY: NO hardcoded dispatch. Every source is called via source.fetch().

        Returns
        -------
        dict with keys: web_data, wiki_data, chat_ctx, has_context,
                        sources_used, confidence_scores
        """
        from engine.confidence_engine import ConfidenceEngine

        ctx: dict = {
            "web_data":           None,
            "wiki_data":          None,
            "chat_ctx":           None,
            "has_context":        False,
            "sources_used":       [],
            "confidence_scores":  {},
            "needs_more_sources": False,
        }

        # ── Inject runtime dependencies into registry ─────────────────────
        from engine.source_registry import configure_web_scraper, configure_chat_log
        if web_scraper:
            configure_web_scraper(web_scraper)
        if chat_log is not None:
            max_turns = getattr(config, "MAX_CHAT_HISTORY", 6)
            configure_chat_log(chat_log, max_turns)

        # ── Get source order for this query (sorted by compute_score) ─────
        sources = KnowledgePlan.plan(intent, query)

        # For knowledge-bearing intents, ensure BOTH web and wikipedia are included
        # (they might not be in the plan if the intent is CHAT or CODING)
        _KNOWLEDGE_INTENTS = {"WEB_SEARCH", "WIKIPEDIA", "UNKNOWN", "REASONING"}
        if intent in _KNOWLEDGE_INTENTS:
            source_names = {s.name for s in sources}

            # Add web if missing
            if "web" not in source_names:
                web_srcs = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)
                web_only = [s for s in web_srcs if s.name == "web"]
                sources = web_only + sources

            # Add wikipedia if missing (as verification/background)
            if "wikipedia" not in source_names:
                wiki_srcs = SourceRegistry.get_sources_for("WIKIPEDIA", available_only=True)
                wiki_only = [s for s in wiki_srcs if s.name == "wikipedia"]
                sources = sources + wiki_only

            # Re-sort by score so the ordering is always dynamic
            sources = sorted(sources, key=lambda s: s.compute_score(), reverse=True)

        # ── Log the plan ──────────────────────────────────────────────────
        plan_names = [f"{s.name}({s.compute_score():.2f})" for s in sources]
        print(Fore.CYAN + f"📋 [Planner]: Source plan → {' → '.join(plan_names)}")

        # ── Fetch from each source in order ───────────────────────────────
        current_confidence = 0.0
        fetched = 0

        for source in sources:
            if fetched >= max_sources:
                break

            # If we have enough confidence from multiple sources, stop
            if current_confidence >= 0.75 and fetched >= 2:
                print(Fore.CYAN + f"✅ [Planner]: Confidence {current_confidence:.2f} ≥ 0.75 with {fetched} sources — stopping.")
                break

            try:
                print(Fore.CYAN + f"🔍 [Planner]: Fetching from '{source.name}' (score={source.compute_score():.2f})...")

                # ── UNIFIED FETCH — source.fetch() handles ALL source-specific logic
                data = source.fetch(query)

                if data and data.strip():
                    data = data.strip()
                    fetched += 1

                    # Store in the correct context key based on source name
                    _store_source_data(ctx, source.name, data)
                    ctx["sources_used"].append(source.name)

                    print(Fore.GREEN + f"✅ [Planner]: {source.name} — {len(data)} chars captured.")

                    # Score this source's data
                    score = ConfidenceEngine.score(
                        answer=data,
                        sources={source.name: data[:300]},
                        source_name=source.name,
                    )
                    ctx["confidence_scores"][source.name] = score
                    current_confidence = max(current_confidence, score)

                    label = ConfidenceEngine.label(score)
                    print(Fore.CYAN + f"🎯 [Planner]: {source.name} confidence = {score:.2f} ({label})")

                    # If confidence is LOW, flag and continue to next source
                    if score < confidence_threshold:
                        ctx["needs_more_sources"] = True
                        print(Fore.YELLOW + f"⚠️  [Planner]: {score:.2f} < {confidence_threshold} — fetching more sources...")
                else:
                    print(Fore.YELLOW + f"⚠️  [Planner]: {source.name} returned empty.")

            except Exception as ex:
                print(Fore.YELLOW + f"⚠️  [Planner]: {source.name} error — {str(ex)[:80]}")

        # ── Summary ───────────────────────────────────────────────────────
        ctx["has_context"] = bool(ctx.get("web_data") or ctx.get("wiki_data"))

        if ctx["sources_used"]:
            merged_label = " + ".join(ctx["sources_used"])
            print(Fore.CYAN + f"🔗 [Planner]: Merged → {merged_label} (best_confidence={current_confidence:.2f})")

        return ctx


def _store_source_data(ctx: dict, source_name: str, data: str) -> None:
    """
    Map a source name to the correct context dict key.

    This is the ONLY place where source names map to context keys.
    New sources can be added by extending this mapping.
    """
    _SOURCE_TO_CTX_KEY = {
        "web":          "web_data",
        "wikipedia":    "wiki_data",
        "chat_history": "chat_ctx",
    }
    key = _SOURCE_TO_CTX_KEY.get(source_name, f"{source_name}_data")
    ctx[key] = data
