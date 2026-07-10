"""
engine/knowledge_planner.py
============================
Generates a KnowledgePlan detailing WHICH sources to query and in what order.
Does NOT execute the fetching itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from engine.source_registry import SourceRegistry, KnowledgeSource
from routing.intent_detector import IntentType

@dataclass
class KnowledgePlan:
    query: str
    intent: IntentType
    sources: list[KnowledgeSource]
    max_sources: int = 3
    confidence_threshold: float = 0.55

class KnowledgePlanner:
    """
    Stateless planner that determines the knowledge gathering strategy.
    """

    @staticmethod
    def plan(
        query: str,
        intent: IntentType,
        max_sources: int = 3,
        confidence_threshold: float = 0.55
    ) -> KnowledgePlan:
        """
        Return a KnowledgePlan with ordered sources for the given intent.
        Ordering is determined by each source's compute_score()
        (freshness*0.4 + authority*0.3 + reliability*0.3).
        """
        # We look up sources using the intent's value (e.g. "FACT_QUERY").
        # If no sources match exactly, we fallback to finding web sources.
        sources = SourceRegistry.get_sources_for(intent.value, available_only=True)

        if not sources:
            # Fallback to web search if we really need knowledge
            sources = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)

        # For FACT_QUERY and REASONING_REQUEST, ensure we have diverse sources
        if intent in (IntentType.FACT_QUERY, IntentType.REASONING_REQUEST):
            source_names = {s.name for s in sources}
            
            # Add web if missing
            if "web" not in source_names:
                web_srcs = SourceRegistry.get_sources_for("WEB_SEARCH", available_only=True)
                sources = [s for s in web_srcs if s.name == "web"] + sources

            # Add wikipedia if missing
            if "wikipedia" not in source_names:
                wiki_srcs = SourceRegistry.get_sources_for("WIKIPEDIA", available_only=True)
                sources = sources + [s for s in wiki_srcs if s.name == "wikipedia"]

            # Re-sort by score
            sources = sorted(sources, key=lambda s: s.compute_score(), reverse=True)

        return KnowledgePlan(
            query=query,
            intent=intent,
            sources=sources,
            max_sources=max_sources,
            confidence_threshold=confidence_threshold
        )
