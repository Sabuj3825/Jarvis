"""
engine/knowledge_planner.py
============================
Dynamic knowledge source planner.

Replaces the hardcoded `_WEB_INTENTS`, `_WIKI_INTENTS`, `_HIST_INTENTS`
frozensets in routing/knowledge_engine.py with a query to the SourceRegistry.

The planner determines at runtime:
  • Which sources are registered
  • Which sources support the current intent
  • Which sources are currently reachable (is_available)
  • The optimal ordering (by priority)

New knowledge sources can now be added by:
  1. Creating a class that implements KnowledgeSource
  2. Calling SourceRegistry.register(instance)
  
No changes to knowledge_engine.py or any routing file needed.

Usage
-----
    from engine.knowledge_planner import KnowledgePlan
    from engine.source_registry import SourceRegistry

    plans = KnowledgePlan.plan(intent="WEB_SEARCH")
    # plans → [WebSearchSource, WikipediaSource] (ordered by priority)

    for plan in plans:
        data = plan.fetch(query)
        if data:
            break
"""

from __future__ import annotations

from .source_registry import SourceRegistry, KnowledgeSource


class KnowledgePlan:
    """
    Static planner — call KnowledgePlan.plan(intent) to get an ordered
    list of knowledge sources appropriate for that intent.
    """

    @staticmethod
    def plan(intent: str) -> list[KnowledgeSource]:
        """
        Return ordered knowledge sources for *intent*.

        Parameters
        ----------
        intent : IntentType string value (e.g. "WEB_SEARCH", "WIKIPEDIA")
        """
        return SourceRegistry.get_sources_for(intent, available_only=True)

    @staticmethod
    def collect_all(
        query: str,
        intent: str,
        max_sources: int = 3,
    ) -> dict[str, str]:
        """
        Fetch from all relevant sources for *intent* and return a dict
        mapping source_name → raw_text.

        Stops after *max_sources* successful fetches to bound latency.

        Parameters
        ----------
        query       : user query (normalized)
        intent      : IntentType string value
        max_sources : maximum number of sources to actually fetch from
        """
        sources = KnowledgePlan.plan(intent)
        results: dict[str, str] = {}
        fetched = 0

        for source in sources:
            if fetched >= max_sources:
                break
            try:
                data = source.fetch(query)
                if data and data.strip():
                    results[source.name] = data.strip()
                    fetched += 1
            except Exception:
                pass

        return results
