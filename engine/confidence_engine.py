"""
engine/confidence_engine.py
============================
Score facts for trustworthiness before they are cached or served to the user.

A confidence score is a float between 0.0 (uncertain) and 1.0 (certain).

Score factors
-------------
  freshness      : how recent is the data? (web data decays, cached data ages)
  reliability    : source reliability rating (defined on each KnowledgeSource)
  agreement      : how many sources agree on the same answer?
  conflict       : did any sources contradict each other?
  length         : very short answers are less trustworthy

Caching threshold (configurable via config.ENGINE_MIN_CACHE_CONFIDENCE):
  Default: 0.6 — only facts with score ≥ 0.6 are written to knowledge.json

Usage
-----
    from engine.confidence_engine import ConfidenceEngine

    score = ConfidenceEngine.score(
        answer      = "The capital of France is Paris.",
        sources     = {"web": "...Paris...", "wikipedia": "...Paris..."},
        has_conflict= False,
    )
    print(score)                  # e.g. 0.82

    if ConfidenceEngine.should_cache(score):
        extract_and_update_knowledge(query, answer)
"""

from __future__ import annotations

from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Source reliability lookup (matches source names in SourceRegistry)
# ─────────────────────────────────────────────────────────────────────────────
_SOURCE_RELIABILITY: dict[str, float] = {
    "web":          0.70,
    "wikipedia":    0.85,
    "chat_history": 0.90,
    "user_verified":1.00,
    "user_override":1.00,
    "react":        0.88,   # multi-source synthesis
    "web+gemini":   0.85,   # gemini-refined web answer
    "gemini":       0.80,
    "ollama":       0.65,
    "openrouter":   0.75,
    "unknown":      0.50,
}

# Minimum answer length to be considered substantive
_MIN_ANSWER_LENGTH = 30

# ─────────────────────────────────────────────────────────────────────────────
# Low-quality phrases that heavily penalize the score
# ─────────────────────────────────────────────────────────────────────────────
_LOW_QUALITY_MARKERS = [
    "as an ai language model",
    "as an ai assistant",
    "i don't have real-time",
    "i do not have real-time",
    "i don't have access to real",
    "i cannot provide",
    "i'm unable to",
    "unable to provide",
    "you might want to check",
    "i cannot confirm",
    "no specific information",
    "i cannot access",
    "i don't know",
    "i am not sure",
]


class ConfidenceEngine:
    """
    Static scorer — call ConfidenceEngine.score() to evaluate a fact.
    """

    @staticmethod
    def score(
        answer: str,
        sources: dict[str, str] | None = None,
        has_conflict: bool = False,
        source_name: str = "unknown",
        min_cache_confidence: float = 0.6,
    ) -> float:
        """
        Compute a confidence score for *answer*.

        Parameters
        ----------
        answer        : the AI-generated or scraped response text
        sources       : dict of {source_name: raw_data} used to generate the answer
        has_conflict  : True if sources disagreed with each other
        source_name   : primary source label (e.g. "web+gemini", "react")
        min_cache_confidence : threshold (not used here; used in should_cache)

        Returns
        -------
        float 0.0 – 1.0
        """
        if not answer or not answer.strip():
            return 0.0

        score = 0.0
        sources = sources or {}

        # ── Factor 1: Source reliability (base score) ─────────────────────────
        reliability = _SOURCE_RELIABILITY.get(source_name, 0.5)
        # If multiple sources used, average their reliabilities
        if sources:
            reliabilities = [
                _SOURCE_RELIABILITY.get(sn, 0.5) for sn in sources.keys()
            ]
            reliability = sum(reliabilities) / len(reliabilities)
        score += reliability * 0.4   # reliability contributes 40%

        # ── Factor 2: Agreement between sources ───────────────────────────────
        num_sources = len(sources)
        if num_sources >= 2:
            agreement_bonus = min(0.2, num_sources * 0.08)  # up to +0.20 for 2+ sources
        elif num_sources == 1:
            agreement_bonus = 0.05
        else:
            agreement_bonus = 0.0
        score += agreement_bonus     # agreement contributes up to 20%

        # ── Factor 3: Conflict penalty ─────────────────────────────────────────
        if has_conflict:
            score -= 0.15

        # ── Factor 4: Answer length / substantiveness ──────────────────────────
        ans_len = len(answer.strip())
        if ans_len >= 200:
            length_score = 0.2
        elif ans_len >= 100:
            length_score = 0.15
        elif ans_len >= _MIN_ANSWER_LENGTH:
            length_score = 0.10
        else:
            length_score = 0.02   # very short answer — suspicious
        score += length_score    # length contributes up to 20%

        # ── Factor 5: Low-quality AI evasion penalty ──────────────────────────
        lower_answer = answer.lower()
        if any(marker in lower_answer for marker in _LOW_QUALITY_MARKERS):
            score -= 0.30        # heavy penalty for evasive / hallucinated responses

        # ── Clamp to [0.0, 1.0] ──────────────────────────────────────────────
        return round(max(0.0, min(1.0, score)), 3)

    @staticmethod
    def should_cache(
        score: float,
        threshold: float = 0.6,
    ) -> bool:
        """
        Return True when *score* meets the minimum threshold for caching.

        Parameters
        ----------
        score     : value from ConfidenceEngine.score()
        threshold : minimum score required (default 0.6 = 60%)
        """
        return score >= threshold

    @staticmethod
    def resolve_conflict(
        fact_a: str,
        score_a: float,
        fact_b: str,
        score_b: float,
    ) -> tuple[str, float]:
        """
        Given two conflicting facts, return the one with the higher confidence.
        If scores are equal, prefer the longer (more detailed) answer.

        Returns (chosen_fact, chosen_score).
        """
        if score_a > score_b:
            return fact_a, score_a
        elif score_b > score_a:
            return fact_b, score_b
        else:
            # Equal confidence — prefer the more detailed answer
            chosen = fact_a if len(fact_a) >= len(fact_b) else fact_b
            return chosen, score_a

    @staticmethod
    def label(score: float) -> str:
        """Return a human-readable confidence label for display/logging."""
        if score >= 0.85:
            return "very_high"
        elif score >= 0.70:
            return "high"
        elif score >= 0.55:
            return "medium"
        elif score >= 0.35:
            return "low"
        else:
            return "very_low"
