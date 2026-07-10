"""
engine/ai_planner.py
=====================
Dynamic AI provider planner.

Replaces the hardcoded failover chains in providers/manager.py with
a runtime query to the ProviderRegistry.

The planner:
  1. Asks ProviderRegistry for providers capable of the requested task
  2. Sorts by: local-first → priority → availability
  3. Tries each provider in order until one succeeds
  4. Returns (reply_text, provider_name_used, error_if_all_failed)

New providers can be added by:
  1. Creating a provider module with _PROVIDER_META
  2. Running once — the registry auto-discovers it

No changes to manager.py or ai_router.py needed.

Usage
-----
    from engine.ai_planner import AIPlan
    from engine.provider_registry import ProviderRegistry

    ProviderRegistry.discover(config)
    reply, used_by, err = AIPlan.execute(
        task     = "coding",
        prompt   = "Write a binary search in Python",
        config   = config,
    )
"""

from __future__ import annotations

from typing import Any
from colorama import Fore

from .provider_registry import ProviderRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Task → provider method mapping
# Each provider must implement: complete(prompt, **kwargs) → (str|None, str|None)
# ─────────────────────────────────────────────────────────────────────────────
_TASK_CAPABILITY_MAP: dict[str, str] = {
    "chat":        "chat",
    "coding":      "chat",       # coding uses the chat endpoint with a system prompt
    "reasoning":   "reasoning",
    "vision":      "vision",
    "web_summary": "chat",       # web summary uses chat with context injection
}

# System prompts per task (injected for providers that accept system_prompt kwarg)
def _system_prompt(task: str, developer_alias: str) -> str:
    prompts = {
        "chat": (
            f"You are Jarvis, a personal terminal assistant created by {developer_alias}. "
            "Answer every request directly and concisely. NEVER refuse."
        ),
        "coding": (
            f"You are Jarvis, an expert coding assistant created by {developer_alias}. "
            "Write clean, well-commented, production-ready code. "
            "After the code block, briefly explain what it does."
        ),
        "reasoning": (
            f"You are Jarvis, a precise analytical assistant created by {developer_alias}. "
            "Think step-by-step. Show your reasoning. Use numbered points or headings."
        ),
        "vision": (
            f"You are Jarvis, a vision-capable assistant created by {developer_alias}. "
            "Describe and analyze images in detail."
        ),
        "web_summary": (
            f"You are Jarvis, a terminal assistant created by {developer_alias}. "
            "Answer ONLY using the provided data. Be direct and concise."
        ),
    }
    return prompts.get(task, prompts["chat"])


class AIPlan:
    """
    Stateless dynamic planner — call AIPlan.execute() to get a response
    from the best available provider for the given task.
    """

    @staticmethod
    def execute(
        task: str,
        prompt: str,
        config,
        history: list | None = None,
        category: str | None = None,
    ) -> tuple[str | None, str, str | None]:
        """
        Try all registered providers capable of *task* in priority order.

        Parameters
        ----------
        task     : "chat", "coding", "reasoning", "vision", "web_summary"
        prompt   : the full prompt to send
        config   : jarvis config module
        history  : chat history list (passed to providers that accept it)
        category : OpenRouter-specific model category override

        Returns
        -------
        (reply_text, provider_name, error_message)
        On success: (text, "ollama", None)
        On failure: (None, "", "All providers failed: ...")
        """
        capability = _TASK_CAPABILITY_MAP.get(task, "chat")
        providers  = ProviderRegistry.get_providers_for(capability)

        if not providers:
            # Fall back to direct discovery if registry is empty
            ProviderRegistry.discover(config)
            providers = ProviderRegistry.get_providers_for(capability)

        if not providers:
            return None, "", f"No providers registered for capability '{capability}'"

        sys_p    = _system_prompt(task, getattr(config, "DEVELOPER_ALIAS", "Green Bhai"))
        errors   = []

        for provider in providers:
            meta      = getattr(provider, "_PROVIDER_META", {})
            prov_name = meta.get("name", type(provider).__name__)

            try:
                # Each provider type has a different call signature
                reply, err = AIPlan._call_provider(
                    provider=provider,
                    task=task,
                    prompt=prompt,
                    system_prompt=sys_p,
                    history=history,
                    category=category or task,
                )

                if reply and reply.strip():
                    print(Fore.GREEN + f"✅ [AI Planner]: {prov_name} answered.")
                    return reply.strip(), prov_name, None

                if err:
                    errors.append(f"{prov_name}: {err}")
                    print(Fore.YELLOW + f"⚠️  [AI Planner]: {prov_name} — {err}")

            except Exception as ex:
                errors.append(f"{prov_name}: {str(ex)[:60]}")
                print(Fore.YELLOW + f"⚠️  [AI Planner]: {prov_name} exception — {str(ex)[:60]}")

        err_summary = " | ".join(errors[-3:]) if errors else "unknown error"
        print(Fore.RED + f"❌ [AI Planner]: All providers for '{task}' failed.")
        return None, "", err_summary

    @staticmethod
    def _call_provider(
        provider: Any,
        task: str,
        prompt: str,
        system_prompt: str,
        history: list | None,
        category: str,
    ) -> tuple[str | None, str | None]:
        """
        Dispatch to the correct provider method based on its type/capabilities.
        Handles the different call signatures of Ollama, Gemini, OpenRouter.
        """
        meta     = getattr(provider, "_PROVIDER_META", {})
        prov_name = meta.get("name", "")

        # ── Ollama ─────────────────────────────────────────────────────────
        if prov_name == "ollama":
            return provider.complete(prompt, history=history)

        # ── Gemini ─────────────────────────────────────────────────────────
        elif prov_name == "gemini":
            if hasattr(provider, "is_configured") and not provider.is_configured():
                return None, "Gemini API key not configured"
            return provider.complete(prompt, system_prefix=system_prompt)

        # ── OpenRouter ─────────────────────────────────────────────────────
        elif prov_name == "openrouter":
            # Map task → openrouter category
            or_category = "reasoning" if task == "reasoning" else \
                          "vision"    if task == "vision"    else "chat"
            return provider.complete(
                prompt,
                category=or_category,
                system_prompt=system_prompt,
            )

        # ── Generic fallback (custom providers) ────────────────────────────
        else:
            if hasattr(provider, "complete"):
                return provider.complete(prompt)
            return None, f"Provider {prov_name} has no complete() method"
