"""
engine/query_normalizer.py
===========================
Normalize user input before it reaches the intent detector or knowledge engine.

Three operations are applied in order:
1. Whitespace normalization (collapse multiple spaces, strip)
2. Abbreviation expansion  (wb → West Bengal, cm → Chief Minister, etc.)
3. Typo correction         (pyhton → python, using a curated dict — zero deps)

All operations are case-insensitive on the input but output is lowercased
(consistent with how jarvis.py already processes input).

Returns a NormalizedQuery dataclass so the caller can see exactly what changed.

Usage
-----
    from engine.query_normalizer import QueryNormalizer

    nq = QueryNormalizer.normalize("pyhton code for wb cm salary")
    print(nq.normalized)       # "python code for west bengal chief minister salary"
    print(nq.corrections_made) # [("pyhton", "python"), ("wb", "west bengal"), ...]
    print(nq.was_changed)      # True
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Abbreviation dictionary
# Format: "abbreviation" -> "expanded form"
# Keys are matched as WHOLE WORDS only (not substrings)
# ─────────────────────────────────────────────────────────────────────────────
_ABBREVIATIONS: dict[str, str] = {
    # Indian geography / government
    "wb":  "west bengal",
    "up":  "uttar pradesh",
    "mp":  "madhya pradesh",
    "ap":  "andhra pradesh",
    "tn":  "tamil nadu",
    "mh":  "maharashtra",
    "ka":  "karnataka",
    "rj":  "rajasthan",
    "gj":  "gujarat",
    "pb":  "punjab",
    "hp":  "himachal pradesh",
    "jk":  "jammu and kashmir",
    "uk":  "uttarakhand",
    "hr":  "haryana",
    "or":  "odisha",
    "br":  "bihar",
    "jh":  "jharkhand",
    "cg":  "chhattisgarh",
    "as":  "assam",
    "mn":  "manipur",
    "mg":  "meghalaya",
    "ml":  "meghalaya",
    "sk":  "sikkim",
    "ar":  "arunachal pradesh",
    "nz":  "nagaland",
    "mi":  "mizoram",
    "tr":  "tripura",
    "dl":  "delhi",
    "mz":  "mizoram",
    "cm":  "chief minister",
    "pm":  "prime minister",
    "dm":  "district magistrate",
    "sp":  "superintendent of police",
    # Technology
    "ai":  "artificial intelligence",
    "ml":  "machine learning",
    "dl":  "deep learning",
    "nlp": "natural language processing",
    "cv":  "computer vision",
    "api": "application programming interface",
    "db":  "database",
    "os":  "operating system",
    "oop": "object oriented programming",
    "sql": "structured query language",
    "ui":  "user interface",
    "ux":  "user experience",
    "ide": "integrated development environment",
    "sdk": "software development kit",
    "gpu": "graphics processing unit",
    "cpu": "central processing unit",
    "ram": "random access memory",
    "llm": "large language model",
    # Common English
    "govt": "government",
    "dept": "department",
    "edu":  "education",
    "info": "information",
    "max":  "maximum",
    "min":  "minimum",
    "avg":  "average",
    "approx": "approximately",
    "curr":   "current",
    "curreng": "current",  # common typo
}

# ─────────────────────────────────────────────────────────────────────────────
# Typo correction dictionary
# Common misspellings in tech queries — pure Python, no external deps
# ─────────────────────────────────────────────────────────────────────────────
_TYPOS: dict[str, str] = {
    # Python ecosystem
    "pyhton":       "python",
    "pytohn":       "python",
    "pythno":       "python",
    "pyton":        "python",
    "ptyhon":       "python",
    "pythn":        "python",
    "phyton":       "python",
    # JavaScript
    "javascipt":    "javascript",
    "javascrpit":   "javascript",
    "javasript":    "javascript",
    "javacript":    "javascript",
    # General programming
    "algorythm":    "algorithm",
    "algortihm":    "algorithm",
    "fucntion":     "function",
    "funciton":     "function",
    "varaiable":    "variable",
    "varibale":     "variable",
    "intialise":    "initialise",
    "initialse":    "initialise",
    "improt":       "import",
    "inport":       "import",
    "pritn":        "print",
    "prnt":         "print",
    "recieve":      "receive",
    "calss":        "class",
    "clas":         "class",
    "retrun":       "return",
    "returun":      "return",
    "dictionray":   "dictionary",
    "dictioary":    "dictionary",
    "exceptiom":    "exception",
    "exeption":     "exception",
    # Common English queries
    "newst":        "newest",
    "lastest":      "latest",
    "latets":       "latest",
    "curent":       "current",
    "currnt":       "current",
    "goverment":    "government",
    "govermnet":    "government",
    "temperture":   "temperature",
    "temprature":   "temperature",
    "wheather":     "weather",
    "wether":       "weather",
    "calender":     "calendar",
    "hitory":       "history",
    "histroy":      "history",
    "explian":      "explain",
    "expain":       "explain",
    "differnce":    "difference",
    "differece":    "difference",
    "defenition":   "definition",
    "defintion":    "definition",
    "sumamry":      "summary",
    "sumarize":     "summarize",
    "searh":        "search",
    "seach":        "search",
    "quesiton":     "question",
    "questoin":     "question",
    "anwser":       "answer",
    "answr":        "answer",
    "knowlege":     "knowledge",
    "knoweldge":    "knowledge",
    "machien":      "machine",
    "leanring":     "learning",
    "artifical":    "artificial",
    "inteligence":  "intelligence",
    "intellegence": "intelligence",
}


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NormalizedQuery:
    original:         str
    normalized:       str
    corrections_made: list[tuple[str, str]] = field(default_factory=list)

    @property
    def was_changed(self) -> bool:
        return self.original.lower().strip() != self.normalized


# ─────────────────────────────────────────────────────────────────────────────
# Normalizer
# ─────────────────────────────────────────────────────────────────────────────

class QueryNormalizer:
    """
    Static utility — call QueryNormalizer.normalize(text) to clean a query.
    """

    @staticmethod
    def normalize(query: str) -> NormalizedQuery:
        """
        Normalize *query* through 3 passes:
          1. Whitespace collapse
          2. Abbreviation expansion (whole-word match)
          3. Typo correction (whole-word match)

        Returns NormalizedQuery with both the original and the cleaned version.
        """
        original = query
        text     = query.lower().strip()
        corrections: list[tuple[str, str]] = []

        # ── Pass 1: Whitespace ────────────────────────────────────────────────
        text = re.sub(r"\s+", " ", text).strip()

        # ── Pass 2: Abbreviation expansion (whole-word boundaries) ────────────
        words = text.split()
        new_words = []
        for w in words:
            clean_w = re.sub(r"[^\w]", "", w)   # strip punctuation for lookup
            if clean_w in _ABBREVIATIONS:
                expanded = _ABBREVIATIONS[clean_w]
                corrections.append((clean_w, expanded))
                # Preserve trailing punctuation on the word if any
                suffix = w[len(clean_w):]
                new_words.append(expanded + suffix)
            else:
                new_words.append(w)
        text = " ".join(new_words)

        # ── Pass 3: Typo correction ───────────────────────────────────────────
        words = text.split()
        new_words = []
        for w in words:
            clean_w = re.sub(r"[^\w]", "", w)
            if clean_w in _TYPOS:
                fixed = _TYPOS[clean_w]
                corrections.append((clean_w, fixed))
                suffix = w[len(clean_w):]
                new_words.append(fixed + suffix)
            else:
                new_words.append(w)
        text = " ".join(new_words)

        return NormalizedQuery(
            original=original,
            normalized=text,
            corrections_made=corrections,
        )
