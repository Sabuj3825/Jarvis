"""
engine/source_registry.py
==========================
Plugin registry for knowledge sources.

Every knowledge source registers itself once (at import time) via:

    SourceRegistry.register(MySource())

Sources must implement the KnowledgeSource interface:

    class KnowledgeSource:
        name              : str          — unique identifier (e.g. "web", "wikipedia")
        supported_intents : frozenset[str]  — IntentType values this source handles
        priority          : int          — higher = tried earlier (default 5)
        reliability       : float        — 0.0–1.0 (used by ConfidenceEngine)
        freshness         : float        — 0.0–1.0 (how current is the data?)
        authority         : float        — 0.0–1.0 (how authoritative is the source?)

        def is_available(self) -> bool: ...
        def fetch(self, query: str, **kwargs) -> str | None: ...

The KnowledgePlanner uses freshness + authority + reliability to dynamically
compute a source score — NO hardcoded source ordering.

Usage
-----
    from engine.source_registry import SourceRegistry

    # Discover all registered sources for a given intent
    sources = SourceRegistry.get_sources_for(intent="WEB_SEARCH")

    # Fetch from all relevant sources
    for source in sources:
        data = source.fetch(query)
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Base interface
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeSource:
    """
    Abstract base class for all knowledge sources.
    Subclass this and call SourceRegistry.register(instance) to plug in.
    """

    name: str = "unnamed_source"
    supported_intents: frozenset = frozenset()  # IntentType string values
    priority: int = 5                            # higher = tried first
    reliability: float = 0.7                     # used by ConfidenceEngine
    freshness: float = 0.5                       # 0.0=stale, 1.0=real-time live
    authority: float = 0.5                       # 0.0=unreliable, 1.0=authoritative

    def is_available(self) -> bool:
        """Return True when this source can be reached right now."""
        return True

    def fetch(self, query: str, **kwargs) -> str | None:
        """
        Fetch knowledge for *query*.
        Returns the raw text, or None if nothing found.
        """
        raise NotImplementedError

    def compute_score(self) -> float:
        """
        Compute a dynamic source score from metadata.
        Used by KnowledgePlanner to sort sources — NOT hardcoded ordering.
        Higher score = tried first.
        """
        # Weighted combination: freshness matters most (40%), then authority (30%), then reliability (30%)
        return (self.freshness * 0.4) + (self.authority * 0.3) + (self.reliability * 0.3)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class SourceRegistry:
    """
    Central registry of all active knowledge sources.

    Sources are registered at module import time.
    New sources can be added without editing any existing file.
    """

    _sources: list[KnowledgeSource] = []

    @classmethod
    def register(cls, source: KnowledgeSource) -> None:
        """Add a knowledge source to the registry."""
        # Avoid duplicates by name
        for existing in cls._sources:
            if existing.name == source.name:
                return
        cls._sources.append(source)

    @classmethod
    def get_sources_for(
        cls,
        intent: str,
        available_only: bool = True,
    ) -> list[KnowledgeSource]:
        """
        Return sources that support *intent*, sorted by compute_score() (highest first).

        Parameters
        ----------
        intent         : IntentType string value (e.g. "WEB_SEARCH")
        available_only : skip sources that report is_available() == False
        """
        matching = [
            s for s in cls._sources
            if intent in s.supported_intents
            and (not available_only or s.is_available())
        ]
        # Sort by dynamic score (computed from freshness, authority, reliability)
        return sorted(matching, key=lambda s: s.compute_score(), reverse=True)

    @classmethod
    def all_sources(cls) -> list[KnowledgeSource]:
        """Return all registered sources."""
        return list(cls._sources)

    @classmethod
    def reset(cls) -> None:
        """Clear registry (used in tests only)."""
        cls._sources = []


# ─────────────────────────────────────────────────────────────────────────────
# Built-in source implementations — registered at import time
# ─────────────────────────────────────────────────────────────────────────────

# Interrogative prefixes to strip before querying Wikipedia
# "who is the chief minister" → "chief minister"
_WIKI_STRIP_PREFIXES = [
    "who is the ", "who is ", "who was the ", "who was ",
    "what is the ", "what is a ", "what is ", "what are the ", "what are ",
    "when is the ", "when is ", "when was the ", "when was ",
    "where is the ", "where is ", "where are the ", "where are ",
    "how is the ", "how is ", "how does the ", "how does ", "how do ",
    "tell me about ", "explain ", "define ",
    "current ", "latest ",
]


def _clean_wiki_query(query: str) -> str:
    """
    Strip interrogative prefixes from a query to produce a clean noun-phrase
    that Wikipedia can match to an article title.

    "who is the chief minister of west bengal" → "chief minister of west bengal"
    "what is machine learning"                 → "machine learning"
    "explain recursion"                        → "recursion"
    """
    q = query.strip()
    q_lower = q.lower()
    for prefix in _WIKI_STRIP_PREFIXES:
        if q_lower.startswith(prefix):
            q = q[len(prefix):]
            break
    return q.strip() if q.strip() else query.strip()


class WebSearchSource(KnowledgeSource):
    """Live web scraper — highest freshness, used for current real-world data."""

    name              = "web"
    supported_intents = frozenset([
        "WEB_SEARCH", "UNKNOWN", "REASONING",
        "WIKIPEDIA",  # available as data source for all knowledge queries
    ])
    priority          = 8
    reliability       = 0.70   # web snippets are decent but not always accurate
    freshness         = 1.0    # ← HIGHEST: live real-time data
    authority         = 0.50   # varies by source website

    def __init__(self, scraper_fn=None):
        self._scraper = scraper_fn  # injected from commands.search_google_scrape

    def set_scraper(self, fn) -> None:
        self._scraper = fn

    def is_available(self) -> bool:
        return self._scraper is not None

    def fetch(self, query: str, **kwargs) -> str | None:
        if not self._scraper:
            return None
        try:
            result = self._scraper(query)
            return result if result and result.strip() else None
        except Exception:
            return None


class WikipediaSource(KnowledgeSource):
    """Wikipedia summary — high authority, good for background/verification."""

    name              = "wikipedia"
    supported_intents = frozenset(["WIKIPEDIA", "WEB_SEARCH", "UNKNOWN", "REASONING"])
    priority          = 7
    reliability       = 0.85  # Wikipedia is generally well-sourced
    freshness         = 0.40  # ← LOWER: Wikipedia can be stale for current events
    authority         = 0.90  # ← HIGH: encyclopedic, well-referenced

    def is_available(self) -> bool:
        try:
            import wikipedia  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, query: str, **kwargs) -> str | None:
        """
        Fetch Wikipedia summary for *query*.

        Key fixes:
        - Strips interrogative prefixes ("who is the" → clean noun phrase)
        - Uses auto_suggest=False to avoid romanized/misdirected articles
        - Falls back to auto_suggest=True if first attempt finds nothing
        """
        try:
            import wikipedia
            clean_q = _clean_wiki_query(query)

            # First attempt: exact match (no auto-suggest misdirection)
            try:
                return wikipedia.summary(clean_q, sentences=4, auto_suggest=False)
            except wikipedia.exceptions.PageError:
                # Page not found with exact query — try with auto-suggest
                try:
                    return wikipedia.summary(clean_q, sentences=4, auto_suggest=True)
                except Exception:
                    return None
            except wikipedia.exceptions.DisambiguationError as e:
                # Take the first suggestion from disambiguation
                if e.options:
                    try:
                        return wikipedia.summary(e.options[0], sentences=4, auto_suggest=False)
                    except Exception:
                        return None
                return None
        except ImportError:
            return None
        except Exception:
            return None


class ChatHistorySource(KnowledgeSource):
    """Recent conversation history — local memory."""

    name              = "chat_history"
    supported_intents = frozenset(["CHAT", "MEMORY", "CODING", "REASONING"])
    priority          = 6
    reliability       = 0.90   # user's own words are highly reliable
    freshness         = 0.80   # current session data
    authority         = 0.60   # user statements, not verified facts

    def __init__(self, chat_log_ref=None, max_turns: int = 6):
        self._chat_log = chat_log_ref or []
        self._max_turns = max_turns

    def set_chat_log(self, log: list, max_turns: int = 6) -> None:
        self._chat_log = log
        self._max_turns = max_turns

    def fetch(self, query: str, **kwargs) -> str | None:
        if not self._chat_log:
            return None
        recent = self._chat_log[-self._max_turns:]
        lines  = []
        for entry in recent:
            role = "You" if entry.get("role") == "user" else "Jarvis"
            text = entry.get("text", "").strip()
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines) if lines else None


# ─── Register built-in sources ───────────────────────────────────────────────
_web_source       = WebSearchSource()
_wiki_source      = WikipediaSource()
_history_source   = ChatHistorySource()

SourceRegistry.register(_web_source)
SourceRegistry.register(_wiki_source)
SourceRegistry.register(_history_source)


def configure_web_scraper(fn) -> None:
    """Call once at startup to inject the web scraper into WebSearchSource."""
    _web_source.set_scraper(fn)


def configure_chat_log(log: list, max_turns: int = 6) -> None:
    """Call once per turn to inject the current chat log into ChatHistorySource."""
    _history_source.set_chat_log(log, max_turns)
