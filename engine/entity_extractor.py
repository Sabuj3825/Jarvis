"""
engine/entity_extractor.py
===========================
Extract named entities and key topics from a user query.

No heavy NLP libraries required — uses pure Python heuristics:
  • Proper noun detection (capitalised words not at sentence start)
  • Known category word lists (countries, cities, languages, tech terms)
  • Stop-word filtering

Returns an EntityResult with the extracted entities as a list of strings.

Usage
-----
    from engine.entity_extractor import EntityExtractor

    result = EntityExtractor.extract("who is the prime minister of India")
    print(result.entities)   # ["India", "prime minister"]
    print(result.topics)     # ["politics", "government"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Stop words — filtered out before entity detection
# ─────────────────────────────────────────────────────────────────────────────
_STOP_WORDS = frozenset([
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "up", "about", "into", "through", "during", "including", "until",
    "against", "among", "throughout", "despite", "towards", "upon",
    "concerning", "of", "to", "in", "for", "on", "with", "at", "by",
    "who", "what", "when", "where", "why", "how", "which", "that", "this",
    "these", "those", "it", "its", "their", "they", "he", "she", "we",
    "you", "i", "me", "him", "her", "us", "them", "my", "your", "his",
    "our", "and", "but", "or", "nor", "so", "yet", "both", "either",
    "neither", "not", "only", "own", "same", "than", "too", "very",
    "just", "don", "t", "s", "tell", "me", "about", "explain", "what",
    "give", "show", "find", "get", "search", "look",
])

# ─────────────────────────────────────────────────────────────────────────────
# Topic keyword → category mapping
# ─────────────────────────────────────────────────────────────────────────────
_TOPIC_CATEGORIES: dict[str, list[str]] = {
    "politics":    ["minister", "president", "government", "election", "parliament",
                    "senate", "congress", "policy", "political", "vote", "party",
                    "chief minister", "prime minister", "governor"],
    "technology":  ["python", "javascript", "java", "code", "program", "algorithm",
                    "software", "hardware", "computer", "ai", "machine learning",
                    "neural", "database", "api", "framework", "library", "linux",
                    "android", "ios", "cloud", "server", "network", "cybersecurity"],
    "science":     ["physics", "chemistry", "biology", "mathematics", "astronomy",
                    "evolution", "quantum", "relativity", "atom", "molecule",
                    "experiment", "theory", "hypothesis", "research", "study"],
    "geography":   ["country", "city", "capital", "state", "river", "mountain",
                    "ocean", "continent", "region", "province", "district", "village"],
    "history":     ["war", "ancient", "century", "civilization", "empire", "dynasty",
                    "revolution", "independence", "colonial", "historical", "founded"],
    "finance":     ["stock", "market", "economy", "gdp", "inflation", "interest",
                    "bank", "currency", "crypto", "bitcoin", "investment", "trade"],
    "sports":      ["cricket", "football", "tennis", "basketball", "olympics",
                    "player", "team", "match", "tournament", "score", "championship"],
    "health":      ["disease", "medicine", "doctor", "hospital", "symptom", "cure",
                    "vaccine", "virus", "health", "medical", "treatment", "diagnosis"],
    "entertainment": ["movie", "film", "actor", "actress", "music", "song", "album",
                      "director", "show", "series", "celebrity", "award"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EntityResult:
    query:    str
    entities: list[str] = field(default_factory=list)   # named entities found
    topics:   list[str] = field(default_factory=list)   # topic categories inferred
    keywords: list[str] = field(default_factory=list)   # important non-stop words


# ─────────────────────────────────────────────────────────────────────────────
# Extractor
# ─────────────────────────────────────────────────────────────────────────────

class EntityExtractor:
    """
    Rule-based entity and topic extractor.
    Pure Python — no external NLP dependencies.
    """

    @staticmethod
    def extract(query: str) -> EntityResult:
        """
        Extract entities, topics, and keywords from *query*.

        Parameters
        ----------
        query : raw or normalized user query (any case)
        """
        result = EntityResult(query=query)

        # ── Proper noun detection (Title-Case words after the first word) ─────
        words = query.split()
        if len(words) > 1:
            for word in words[1:]:
                clean = re.sub(r"[^\w]", "", word)
                if (
                    clean
                    and clean[0].isupper()
                    and len(clean) > 1
                    and clean.lower() not in _STOP_WORDS
                ):
                    result.entities.append(clean)

        # ── Keyword extraction (meaningful non-stop words) ────────────────────
        lower_words = query.lower().split()
        keywords = []
        for w in lower_words:
            clean = re.sub(r"[^\w]", "", w)
            if clean and clean not in _STOP_WORDS and len(clean) > 2:
                keywords.append(clean)
        result.keywords = list(dict.fromkeys(keywords))  # preserve order, dedupe

        # ── Topic classification ───────────────────────────────────────────────
        lower_query = query.lower()
        found_topics = []
        for topic, signals in _TOPIC_CATEGORIES.items():
            if any(signal in lower_query for signal in signals):
                found_topics.append(topic)
        result.topics = found_topics

        # ── Deduplicate entities ───────────────────────────────────────────────
        seen = set()
        unique_entities = []
        for e in result.entities:
            if e.lower() not in seen:
                seen.add(e.lower())
                unique_entities.append(e)
        result.entities = unique_entities

        return result
