"""
providers/manager.py
=====================
ProviderManager — the single entry point for all AI calls in JARVIS.

v8: Delegates entirely to engine.ai_planner.AIPlan which dynamically queries the
    ProviderRegistry for the best available provider at runtime based on capabilities.

Failover is fully dynamic:
  - Local providers are prioritized for specific capabilities (e.g., chat)
  - Cloud providers are prioritized for advanced reasoning/coding
  - Order is determined by _PROVIDER_META.priority per capability
"""

from __future__ import annotations

from colorama import Fore

from .ollama_provider    import OllamaProvider
from .gemini_provider    import GeminiProvider
from .openrouter_provider import OpenRouterProvider

from engine.ai_planner       import AIPlan
from engine.provider_registry import ProviderRegistry

# ─────────────────────────────────────────────────────────────────────────────
# Quality filter — phrases that indicate an evasive / useless response
# ─────────────────────────────────────────────────────────────────────────────
_LOW_QUALITY = frozenset([
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
])


def _is_quality(response: str | None) -> bool:
    """Return True when the response is substantive — not an AI evasion."""
    if not response or len(response.strip()) < 10:
        return False
    lower = response.lower()
    return not any(marker in lower for marker in _LOW_QUALITY)


class ProviderManager:
    """
    Unified AI facade with automatic provider selection and failover.
    """

    def __init__(self, config):
        self._config    = config
        self.ollama     = OllamaProvider(config)
        self.gemini     = GeminiProvider(config)
        self.openrouter = OpenRouterProvider(config)

        # Seed the provider registry once per ProviderManager instance
        if not ProviderRegistry.all_providers():
            ProviderRegistry.register(self.ollama)
            ProviderRegistry.register(self.gemini)
            ProviderRegistry.register(self.openrouter)

    def chat(self, prompt: str, history: list | None = None) -> str:
        """General conversational response with chat-history context."""
        print(Fore.CYAN + "🧠 [Manager]: CHAT pipeline (dynamic)")
        reply, provider, err = AIPlan.execute(
            task="chat", prompt=prompt, config=self._config, history=history
        )
        if reply:
            return reply
        print(Fore.RED + f"❌ [Manager]: All CHAT providers failed — {err}")
        return "❌ All AI providers are currently unavailable."

    def coding(self, prompt: str) -> str:
        """Code generation and debugging — best model tried first."""
        print(Fore.CYAN + "💻 [Manager]: CODING pipeline (dynamic)")
        reply, provider, err = AIPlan.execute(
            task="coding", prompt=prompt, config=self._config
        )
        if reply:
            return reply
        print(Fore.RED + f"❌ [Manager]: All CODING providers failed — {err}")
        return "❌ All coding AI providers are currently unavailable."

    def reasoning(self, prompt: str) -> str:
        """Analytical, multi-step reasoning — dedicated reasoning models first."""
        print(Fore.CYAN + "🧮 [Manager]: REASONING pipeline (dynamic)")
        reply, provider, err = AIPlan.execute(
            task="reasoning", prompt=prompt, config=self._config
        )
        if reply:
            return reply
        print(Fore.RED + f"❌ [Manager]: All REASONING providers failed — {err}")
        return "❌ All reasoning AI providers are currently unavailable."

    def vision(self, prompt: str) -> str:
        """Image/visual analysis — vision-capable models only."""
        print(Fore.CYAN + "👁️  [Manager]: VISION pipeline (dynamic)")
        reply, provider, err = AIPlan.execute(
            task="vision", prompt=prompt, config=self._config
        )
        if reply:
            return reply
        print(Fore.RED + f"❌ [Manager]: All VISION providers failed — {err}")
        return "❌ Vision capabilities are currently unavailable."

    def web_summary(self, prompt: str, knowledge_ctx: dict) -> str:
        """
        Synthesise an answer from pre-collected web / Wikipedia data.
        Falls back through all providers, then serves raw data if all fail.
        """
        print(Fore.CYAN + "🌐 [Manager]: WEB SUMMARY pipeline (dynamic)")

        parts: list[str] = []
        if knowledge_ctx.get("web_data"):
            parts.append(f"[Live Web Data]\n{knowledge_ctx['web_data']}")
        if knowledge_ctx.get("wiki_data"):
            parts.append(f"[Wikipedia Background]\n{knowledge_ctx['wiki_data']}")

        if parts:
            context = "\n\n".join(parts)
            enriched_prompt = (
                f"You are Jarvis, a terminal assistant created by {self._config.DEVELOPER_ALIAS}. "
                f"Answer ONLY using the data below. Be direct and concise.\n\n"
                f"{context}\n\nQuery: {prompt}"
            )
        else:
            enriched_prompt = prompt

        reply, provider, err = AIPlan.execute(
            task="web_summary", prompt=enriched_prompt, config=self._config
        )
        if reply and _is_quality(reply):
            return reply
        if reply:
            print(Fore.YELLOW + "⚠️  Low-quality summary — serving raw data instead.")

        print(Fore.RED + "❌ [Manager]: All summary providers failed.")
        if knowledge_ctx.get("web_data"):
            print(Fore.YELLOW + "⚠️  Serving raw web data.")
            return knowledge_ctx["web_data"]
        if knowledge_ctx.get("wiki_data"):
            print(Fore.YELLOW + "⚠️  Serving raw Wikipedia data.")
            return knowledge_ctx["wiki_data"]

        return "❌ No AI providers available and no cached data found for that query."

