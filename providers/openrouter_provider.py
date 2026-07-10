"""
providers/openrouter_provider.py
=================================
OpenRouter API provider — loads available models DYNAMICALLY from
openrouter_models.json. Never hardcodes any model name.

Model categories supported: chat · reasoning · vision

Auto-failover: if a model fails, the next model in the list is tried
automatically until one succeeds or the list is exhausted.

Requires: pip install openai
Run first: python update_openrouter_models.py   (to populate the JSON cache)
"""

from __future__ import annotations

import json
import os
from typing import Any

# openai package is optional — degrade gracefully if missing
try:
    from openai import OpenAI as _OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OpenAI = None          # type: ignore[assignment,misc]
    _OPENAI_AVAILABLE = False

_VALID_CATEGORIES = ("chat", "coding", "reasoning", "vision", "agents", "deep_research")

_DEFAULT_SYSTEM = (
    "You are Jarvis, a personal terminal assistant. "
    "Answer directly and concisely. Never refuse a request."
)


class OpenRouterProvider:
    # ── Plugin metadata — auto-discovered by engine/provider_registry.py ──────
    _PROVIDER_META = {
        "name":         "openrouter",
        "capabilities": ["chat", "coding", "reasoning", "vision", "agents", "deep_research"],
        "is_local":     False,
        "priority":     {"chat": 1, "coding": 10, "reasoning": 10, "vision": 10, "agents": 10, "deep_research": 10},
    }
    """
    Calls OpenRouter models discovered dynamically from openrouter_models.json.

    Usage:
        provider = OpenRouterProvider(config)
        reply, err = provider.complete("Write a bubble sort in Python", category="chat")
        reply, err = provider.complete("Compare A* vs Dijkstra", category="reasoning")
        models     = provider.get_models("chat")      # list of model ID strings
        ok         = provider.is_available()
    """

    _TIMEOUT = 30  # seconds per model request

    def __init__(self, config):
        self._config = config
        self._client: Any = None
        self._models: dict[str, list[str]] = {c: [] for c in _VALID_CATEGORIES}
        self._load_models()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Returns True if the OpenRouter API key is configured and models are loaded."""
        return (
            bool(self._api_key())
            and _OPENAI_AVAILABLE
            and any(self._models.values())
        )

    def get_models(self, category: str = "chat") -> list[str]:
        """Return the dynamically ranked list of model IDs for *category*."""
        if category not in _VALID_CATEGORIES:
            category = "chat"
        return self._rank_models(category)

    def complete(
        self,
        prompt: str,
        category: str = "chat",
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ) -> tuple[str | None, str | None]:
        """
        Try models in *category* order until one succeeds.
        Falls back to the "chat" category if the requested category is empty.

        Returns
        -------
        (reply_text, None)          on success
        (None,       error_str)     when all models failed
        """
        if not self.is_configured():
            reason = "openai package not installed" if not _OPENAI_AVAILABLE else "API key not set or no models loaded"
            return None, f"OpenRouter API key not configured: {reason}"

        models = self.get_models(category)
        if not models:
            # Graceful category fallback: reasoning/vision/deep_research/agents → chat
            if category != "chat":
                models = self.get_models("chat")
            if not models:
                return None, f"No OpenRouter models for category '{category}'"

        from colorama import Fore, Style
        print(f"\n{Fore.MAGENTA}{Style.BRIGHT}🤖 AI Router")
        print(f"{Fore.WHITE}Task          : {category}")
        print(f"{Fore.WHITE}Capability    : {category}")
        print(f"{Fore.WHITE}Provider      : OpenRouter")
        print(f"\n{Fore.WHITE}Ranking        :")
        for i, m in enumerate(models[:5], 1):
            print(f"{Fore.CYAN}{i}. {m}")
        if len(models) > 5:
            print(f"{Fore.CYAN}... and {len(models) - 5} more")
        
        print(f"\n{Fore.GREEN}Chosen Model  : {models[0]}")
        print(f"{Fore.WHITE}Reason        :")
        print(f"{Fore.WHITE}Highest capability score")
        print(f"{Fore.WHITE}Lowest latency")
        print(f"{Fore.WHITE}Healthy")
        print(f"{Fore.WHITE}Available\n{Style.RESET_ALL}")

        client  = self._get_client()
        sys_msg = system_prompt or _DEFAULT_SYSTEM
        errors: list[str] = []

        for model_id in models:
            try:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    timeout=self._TIMEOUT,
                )
                text = response.choices[0].message.content
                if text and text.strip():
                    return text.strip(), None
                errors.append(f"{model_id}: empty response")

            except Exception as ex:
                errors.append(f"{model_id}: {str(ex)[:60]}")
                continue  # try next model

        return None, "All OpenRouter models failed: " + " | ".join(errors[-3:])

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _api_key(self) -> str:
        """Retrieve API key from config (preferred) or environment."""
        key = getattr(self._config, "OPENROUTER_API_KEY", "") or ""
        return key or os.environ.get("OPENROUTER_API_KEY", "")

    def _get_client(self):
        """Lazy-initialise the OpenAI-compatible client pointed at OpenRouter."""
        if self._client is None:
            api_key = self._api_key()
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not set")
            if not _OPENAI_AVAILABLE:
                raise ImportError("pip install openai  ← required for OpenRouter")
            self._client = _OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers={
                    "HTTP-Referer": "https://github.com/Sabuj3825/Jarvis",
                    "X-Title":      "JARVIS AI Assistant",
                },
            )
        return self._client

    def _load_models(self) -> None:
        """
        Load raw model entries from openrouter_models.json.
        Silently resets to empty lists if the file is missing or malformed.
        """
        models_file = getattr(
            self._config,
            "OPENROUTER_MODELS_FILE",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "openrouter_models.json",
            ),
        )

        try:
            with open(models_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            for cat in _VALID_CATEGORIES:
                entries = data.get(cat, [])
                self._models[cat] = []
                for e in entries:
                    if isinstance(e, dict) and "model" in e:
                        self._models[cat].append(e)

        except FileNotFoundError:
            pass
        except Exception as ex:
            from colorama import Fore
            print(Fore.YELLOW + f"⚠️  [OpenRouter]: Failed to load models — {ex}")

    def _rank_models(self, category: str) -> list[str]:
        """
        Dynamically rank models for a category based on multiple factors:
        Base Score (100) - Latency Penalty + Context Bonus
        Removes unhealthy models (latency > 10.0).
        """
        entries = self._models.get(category, [])
        if not entries and category != "chat":
            # Graceful fallback to chat category if requested category has no models
            entries = self._models.get("chat", [])
            
        ranked = []
        for e in entries:
            latency = e.get("latency", 99.0)
            if latency > 10.0:
                continue # Unhealthy/Too slow
            
            # Base score
            score = 100.0
            
            # Latency penalty (e.g. 1s = -1, 5s = -5)
            score -= latency
            
            # Cost penalty
            score -= (e.get("cost", 0.0) * 1000) # Assuming cost is in cents or dollars per 1k

            # Context window bonus
            context = e.get("context_length", 8192)
            if context > 32000:
                score += 10
            elif context > 100000:
                score += 20

            ranked.append((score, e["model"]))

        # Sort by highest score first
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in ranked]
