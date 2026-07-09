"""
providers/manager.py
=====================
ProviderManager — the single entry point for all AI calls in JARVIS.

Implements fully automatic failover chains for every task type:

  CHAT       : Ollama → Gemini → OpenRouter (chat)
  CODING     : OpenRouter (chat) → Gemini → Ollama
  REASONING  : OpenRouter (reasoning) → Gemini → Ollama
  VISION     : OpenRouter (vision) → Gemini
  WEB_SUMMARY: Ollama → Gemini → OpenRouter → raw data fallback

The caller never needs to know which provider actually answered.
"""

from __future__ import annotations

from colorama import Fore

from .ollama_provider import OllamaProvider
from .gemini_provider import GeminiProvider
from .openrouter_provider import OpenRouterProvider

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

    Instantiate once per user turn:
        mgr = ProviderManager(config)
        reply = mgr.chat("Hello")
        reply = mgr.coding("Write a bubble sort in Python")
        reply = mgr.reasoning("Compare async vs sync programming")
        reply = mgr.web_summary("AI news", {"web_data": "...", "wiki_data": "..."})
    """

    def __init__(self, config):
        self._config    = config
        self.ollama     = OllamaProvider(config)
        self.gemini     = GeminiProvider(config)
        self.openrouter = OpenRouterProvider(config)

    # ─────────────────────────────────────────────────────────────────────────
    # CHAT — Ollama → Gemini → OpenRouter chat
    # ─────────────────────────────────────────────────────────────────────────
    def chat(self, prompt: str, history: list | None = None) -> str:
        """General conversational response with chat-history context."""
        print(Fore.CYAN + "🧠 [Manager]: CHAT pipeline — Ollama → Gemini → OpenRouter")

        r, err = self.ollama.complete(prompt, history=history)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Ollama answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: Ollama — {err}")

        r, err = self.gemini.complete(
            prompt,
            system_prefix=(
                f"You are Jarvis, a terminal assistant created by {self._config.DEVELOPER_ALIAS}. "
                "Answer directly and concisely."
            ),
        )
        if r:
            print(Fore.GREEN + "✅ [Manager]: Gemini answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: Gemini — {err}")

        r, err = self.openrouter.complete(prompt, category="chat")
        if r:
            print(Fore.GREEN + "✅ [Manager]: OpenRouter (chat) answered.")
            return r
        print(Fore.RED + f"❌ [Manager]: All CHAT providers failed — {err}")
        return "❌ All AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # CODING — OpenRouter → Gemini → Ollama
    # ─────────────────────────────────────────────────────────────────────────
    def coding(self, prompt: str) -> str:
        """Code generation and debugging — best model tried first."""
        print(Fore.CYAN + "💻 [Manager]: CODING pipeline — OpenRouter → Gemini → Ollama")

        sys_p = (
            f"You are Jarvis, an expert coding assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Write clean, well-commented, production-ready code. "
            "After the code block, briefly explain what it does."
        )

        r, err = self.openrouter.complete(prompt, category="chat", system_prompt=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: OpenRouter (coding) answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: OpenRouter coding — {err}")

        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Gemini (coding) answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: Gemini coding — {err}")

        r, err = self.ollama.complete(prompt)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Ollama (coding) answered.")
            return r

        print(Fore.RED + "❌ [Manager]: All CODING providers failed.")
        return "❌ All coding AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # REASONING — OpenRouter reasoning → Gemini → Ollama
    # ─────────────────────────────────────────────────────────────────────────
    def reasoning(self, prompt: str) -> str:
        """Analytical, multi-step reasoning — dedicated reasoning models first."""
        print(Fore.CYAN + "🧮 [Manager]: REASONING pipeline — OpenRouter reasoning → Gemini → Ollama")

        sys_p = (
            f"You are Jarvis, a precise analytical assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Think step-by-step. Show your reasoning. Use numbered points or headings."
        )

        r, err = self.openrouter.complete(prompt, category="reasoning", system_prompt=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: OpenRouter (reasoning) answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: OpenRouter reasoning — {err}")

        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Gemini (reasoning) answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: Gemini reasoning — {err}")

        r, err = self.ollama.complete(prompt)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Ollama (reasoning) answered.")
            return r

        print(Fore.RED + "❌ [Manager]: All REASONING providers failed.")
        return "❌ All reasoning AI providers are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # VISION — OpenRouter vision → Gemini
    # ─────────────────────────────────────────────────────────────────────────
    def vision(self, prompt: str) -> str:
        """Image/visual analysis — vision-capable models only."""
        print(Fore.CYAN + "👁️  [Manager]: VISION pipeline — OpenRouter vision → Gemini")

        sys_p = (
            f"You are Jarvis, a vision-capable assistant created by {self._config.DEVELOPER_ALIAS}. "
            "Describe and analyze images in detail."
        )

        r, err = self.openrouter.complete(prompt, category="vision", system_prompt=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: OpenRouter (vision) answered.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: OpenRouter vision — {err}")

        r, err = self.gemini.complete(prompt, system_prefix=sys_p)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Gemini (vision) answered.")
            return r

        print(Fore.RED + "❌ [Manager]: All VISION providers failed.")
        return "❌ Vision capabilities are currently unavailable."

    # ─────────────────────────────────────────────────────────────────────────
    # WEB_SUMMARY — Ollama → Gemini → OpenRouter → raw data
    # ─────────────────────────────────────────────────────────────────────────
    def web_summary(self, prompt: str, knowledge_ctx: dict) -> str:
        """
        Synthesise an answer from pre-collected web / Wikipedia data.
        Falls back through all providers, then serves raw data if all fail.

        knowledge_ctx keys used:
            web_data  : str | None
            wiki_data : str | None
        """
        print(Fore.CYAN + "🌐 [Manager]: WEB SUMMARY pipeline — Ollama → Gemini → OpenRouter → raw")

        # Build the enriched prompt
        parts: list[str] = []
        if knowledge_ctx.get("web_data"):
            parts.append(f"[Live Web Data]\n{knowledge_ctx['web_data']}")
        if knowledge_ctx.get("wiki_data"):
            parts.append(f"[Wikipedia Background]\n{knowledge_ctx['wiki_data']}")

        if parts:
            context = "\n\n".join(parts)
            synthesise_prompt = (
                f"You are Jarvis, a terminal assistant created by {self._config.DEVELOPER_ALIAS}. "
                f"Answer ONLY using the data below. Be direct and concise.\n\n"
                f"{context}\n\n"
                f"Query: {prompt}"
            )
        else:
            synthesise_prompt = prompt

        # Ollama (fast, local — quality check applied)
        r, err = self.ollama.complete(synthesise_prompt)
        if r and _is_quality(r):
            print(Fore.GREEN + "✅ [Manager]: Ollama summarised knowledge context.")
            return r
        if r:
            print(Fore.YELLOW + "⚠️  [Manager]: Ollama gave low-quality summary, escalating...")
        else:
            print(Fore.YELLOW + f"⚠️  [Manager]: Ollama — {err}")

        # Gemini
        r, err = self.gemini.complete(synthesise_prompt)
        if r:
            print(Fore.GREEN + "✅ [Manager]: Gemini summarised knowledge context.")
            return r
        print(Fore.YELLOW + f"⚠️  [Manager]: Gemini — {err}")

        # OpenRouter
        r, err = self.openrouter.complete(synthesise_prompt, category="chat")
        if r:
            print(Fore.GREEN + "✅ [Manager]: OpenRouter summarised knowledge context.")
            return r
        print(Fore.RED + f"❌ [Manager]: All summary providers failed.")

        # Raw data fallback — always return something
        if knowledge_ctx.get("web_data"):
            print(Fore.YELLOW + "⚠️  [Manager]: Serving raw web data.")
            return knowledge_ctx["web_data"]
        if knowledge_ctx.get("wiki_data"):
            print(Fore.YELLOW + "⚠️  [Manager]: Serving raw Wikipedia data.")
            return knowledge_ctx["wiki_data"]

        return "❌ No AI providers available and no cached data found for that query."
