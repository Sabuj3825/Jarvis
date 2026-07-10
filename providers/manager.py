"""
providers/manager.py
=====================
ProviderManager — the single entry point for all AI calls in JARVIS.

v7: Delegates to engine.ai_planner.AIPlan which dynamically queries the
    ProviderRegistry for the best available provider at runtime.

Failover is now fully dynamic:
  - Local providers are always tried first (Local-First policy)
  - Order is determined by _PROVIDER_META.priority
  - Adding a new provider requires ZERO changes here

The caller (ai_router.py) never needs to know which provider answered.
"""

from __future__ import annotations

from colorama import Fore

from .ollama_provider    import OllamaProvider
from .gemini_provider    import GeminiProvider
from .openrouter_provider import OpenRouterProvider

# ── Engine layer (dynamic planner) ────────────────────────────────────────────
try:
    from engine.ai_planner       import AIPlan
    from engine.provider_registry import ProviderRegistry
    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE_AVAILABLE = False

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

    v7: Uses the dynamic AIPlan engine when available.
        Falls back to direct provider calls when engine/ is not importable.

    Instantiate once per user turn:
        mgr = ProviderManager(config)
        reply = mgr.chat("Hello")
        reply = mgr.coding("Write a bubble sort in Python")
    """

    def __init__(self, config):
        self._config    = config
        self.ollama     = OllamaProvider(config)
        self.gemini     = GeminiProvider(config)
        self.openrouter = OpenRouterProvider(config)

        # Seed the provider registry once per ProviderManager instance
        if _ENGINE_AVAILABLE:
            if not ProviderRegistry.all_providers():
                ProviderRegistry.register(self.ollama)
                ProviderRegistry.register(self.gemini)
                ProviderRegistry.register(self.openrouter)

    # ─────────────────────────────────────────────────────────────────────────
    # CHAT
    # ─────────────────────────────────────────────────────────────────────────
    def chat(self, prompt: str, history: list | None = None) -> str:
        """General conversational response with chat-history context."""
        print(Fore.CYAN + "🧠 [Manager]: CHAT pipeline (dynamic)")

        if _ENGINE_AVAILABLE:
            reply, provider, err = AIPlan.execute(
                task="chat", prompt=prompt, config=self._config, history=history
            )
            if reply:
                return reply
            print(Fore.RED + f"❌ [Manager]: All CHAT providers failed — {err}")
            return "❌ All AI providers are currently unavailable."

        # ── Legacy fallback ───────────────────────────────────────────────
        print(Fore.CYAN + "   (legacy: Ollama → Gemini → OpenRouter)")
        r, err = self.ollama.complete(prompt, history=history)
        if r:
            print(Fore.GREEN + "✅ Ollama answered.")
            return r
        print(Fore.YELLOW + f"⚠️  Ollama — {err}")

        r, err = self.gemini.complete(
            prompt,
            system_prefix=(
                f"You are Jarvis, a terminal assistant created by {self._config.DEVELOPER_ALIAS}. "
                "Answer directly and concisely."
            ),
        )
        if r:
            print(Fore.GREEN + "✅ Gemini answered.")
            return r
        print(Fore.YELLOW + f"⚠️  Gemini — {err}")

        r, err = self.openrouter.complete(prompt, category="chat")
        if r:
            print(Fore.GREEN + "✅ OpenRouter answered.")
            return r
        print(Fore.RED + f"❌ All CHAT providers failed — {err}")
        return "❌ All AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # CODING
    # ─────────────────────────────────────────────────────────────────────────
    def coding(self, prompt: str) -> str:
        """Code generation and debugging — best model tried first."""
        print(Fore.CYAN + "💻 [Manager]: CODING pipeline (dynamic)")

        if _ENGINE_AVAILABLE:
            reply, provider, err = AIPlan.execute(
                task="coding", prompt=prompt, config=self._config
            )
            if reply:
                return reply
            print(Fore.RED + f"❌ [Manager]: All CODING providers failed — {err}")
            return "❌ All coding AI providers are currently unavailable."

        # ── Legacy fallback ───────────────────────────────────────────────
        sys_p = (
            f"You are Jarvis, an expert coding assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Write clean, well-commented, production-ready code."
        )
        print(Fore.CYAN + "   (legacy: OpenRouter → Gemini → Ollama)")
        r, err = self.openrouter.complete(prompt, category="chat", system_prompt=sys_p)
        if r:
            return r
        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            return r
        r, err = self.ollama.complete(prompt)
        if r:
            return r
        return "❌ All coding AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # REASONING
    # ─────────────────────────────────────────────────────────────────────────
    def reasoning(self, prompt: str) -> str:
        """Analytical, multi-step reasoning — dedicated reasoning models first."""
        print(Fore.CYAN + "🧮 [Manager]: REASONING pipeline (dynamic)")

        if _ENGINE_AVAILABLE:
            reply, provider, err = AIPlan.execute(
                task="reasoning", prompt=prompt, config=self._config
            )
            if reply:
                return reply
            print(Fore.RED + f"❌ [Manager]: All REASONING providers failed — {err}")
            return "❌ All reasoning AI providers are currently unavailable."

        # ── Legacy fallback ───────────────────────────────────────────────
        sys_p = (
            f"You are Jarvis, a precise analytical assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Think step-by-step."
        )
        print(Fore.CYAN + "   (legacy: OpenRouter → Gemini → Ollama)")
        r, err = self.openrouter.complete(prompt, category="reasoning", system_prompt=sys_p)
        if r:
            return r
        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            return r
        r, err = self.ollama.complete(prompt)
        if r:
            return r
        return "❌ All reasoning AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # VISION
    # ─────────────────────────────────────────────────────────────────────────
    def vision(self, prompt: str) -> str:
        """Image/visual analysis — vision-capable models only."""
        print(Fore.CYAN + "👁️  [Manager]: VISION pipeline (dynamic)")

        if _ENGINE_AVAILABLE:
            reply, provider, err = AIPlan.execute(
                task="vision", prompt=prompt, config=self._config
            )
            if reply:
                return reply
            print(Fore.RED + f"❌ [Manager]: All VISION providers failed — {err}")
            return "❌ Vision capabilities are currently unavailable."

        # ── Legacy fallback ───────────────────────────────────────────────
        sys_p = (
            f"You are Jarvis, a vision-capable assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Describe and analyze images in detail."
        )
        print(Fore.CYAN + "   (legacy: OpenRouter vision → Gemini)")
        r, err = self.openrouter.complete(prompt, category="vision", system_prompt=sys_p)
        if r:
            return r
        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            return r
        return "❌ Vision capabilities are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # WEB_SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    def web_summary(self, prompt: str, knowledge_ctx: dict) -> str:
        """
        Synthesise an answer from pre-collected web / Wikipedia data.
        Falls back through all providers, then serves raw data if all fail.
        """
        print(Fore.CYAN + "🌐 [Manager]: WEB SUMMARY pipeline (dynamic)")

        # Build the enriched prompt
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

        if _ENGINE_AVAILABLE:
            reply, provider, err = AIPlan.execute(
                task="web_summary", prompt=enriched_prompt, config=self._config
            )
            if reply and _is_quality(reply):
                return reply
            if reply:
                print(Fore.YELLOW + "⚠️  Low-quality summary — serving raw data instead.")
        else:
            # ── Legacy fallback ────────────────────────────────────────────
            print(Fore.CYAN + "   (legacy: Ollama → Gemini → OpenRouter → raw)")
            r, err = self.ollama.complete(enriched_prompt)
            if r and _is_quality(r):
                print(Fore.GREEN + "✅ Ollama summarised.")
                return r
            r, err = self.gemini.complete(enriched_prompt)
            if r:
                print(Fore.GREEN + "✅ Gemini summarised.")
                return r
            r, err = self.openrouter.complete(enriched_prompt, category="chat")
            if r:
                print(Fore.GREEN + "✅ OpenRouter summarised.")
                return r

        # Raw data fallback — always return something
        print(Fore.RED + "❌ [Manager]: All summary providers failed.")
        if knowledge_ctx.get("web_data"):
            print(Fore.YELLOW + "⚠️  Serving raw web data.")
            return knowledge_ctx["web_data"]
        if knowledge_ctx.get("wiki_data"):
            print(Fore.YELLOW + "⚠️  Serving raw Wikipedia data.")
            return knowledge_ctx["wiki_data"]

        return "❌ No AI providers available and no cached data found for that query."

