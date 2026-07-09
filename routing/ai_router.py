"""
routing/ai_router.py
=====================
Final routing step — maps an IntentType + knowledge context to the correct
ProviderManager pipeline.

This is the last layer before the response is generated. It:
  1. Instantiates ProviderManager (which loads all providers lazily)
  2. Builds task-specific prompts from the collected knowledge
  3. Calls the correct manager method (chat / coding / reasoning / vision / web_summary)
  4. Returns the final reply string

Call hierarchy:
    jarvis.py  →  AIRouter.route()  →  ProviderManager.<method>()
                                    →  OllamaProvider / GeminiProvider / OpenRouterProvider
"""

from __future__ import annotations

from colorama import Fore

from .intent_detector import IntentType
from providers.manager import ProviderManager


class AIRouter:
    """
    Stateless router — all logic lives in the single static method `route()`.

    Usage:
        reply = AIRouter.route(
            user_input      = user_input,        # original (unprocessed) text
            processed_input = processed_input,   # lowercase stripped version
            intent          = intent,            # IntentType from detector
            knowledge_ctx   = ctx,               # dict from KnowledgeEngine
            config          = config,            # jarvis config module
            chat_log        = config.chat_log,   # for CHAT / MEMORY intents
        )
    """

    @staticmethod
    def route(
        user_input: str,
        processed_input: str,
        intent: IntentType,
        knowledge_ctx: dict,
        config,
        chat_log: list | None = None,
    ) -> str:
        """
        Route to the correct provider chain and return the AI response.

        Parameters
        ----------
        user_input      : original user text (unmodified)
        processed_input : lowercased, stripped version of user input
        intent          : IntentType from IntentDetector.detect()
        knowledge_ctx   : context dict from KnowledgeEngine.collect()
        config          : jarvis config module
        chat_log        : session chat log (needed for CHAT/MEMORY intents)
        """
        mgr = ProviderManager(config)

        print(Fore.MAGENTA + f"⚡ [AI Router]: Intent → {intent.value}")

        # ── LOCAL_COMMAND ─────────────────────────────────────────────────────
        if intent == IntentType.LOCAL_COMMAND:
            # Should never reach here — commands.handle_command() catches these
            # before jarvis.py calls the routing system.  Soft fallback only.
            return mgr.chat(user_input, history=chat_log)

        # ── CODING ───────────────────────────────────────────────────────────
        elif intent == IntentType.CODING:
            prompt = _coding_prompt(user_input, knowledge_ctx)
            return mgr.coding(prompt)

        # ── REASONING ────────────────────────────────────────────────────────
        elif intent == IntentType.REASONING:
            if knowledge_ctx.get("has_context"):
                prompt = _research_prompt(user_input, knowledge_ctx, config)
            else:
                prompt = user_input
            return mgr.reasoning(prompt)

        # ── VISION ───────────────────────────────────────────────────────────
        elif intent == IntentType.VISION:
            return mgr.vision(user_input)

        # ── WEB_SEARCH / WIKIPEDIA / UNKNOWN ─────────────────────────────────
        elif intent in (IntentType.WEB_SEARCH, IntentType.WIKIPEDIA, IntentType.UNKNOWN):
            return mgr.web_summary(user_input, knowledge_ctx)

        # ── MEMORY ───────────────────────────────────────────────────────────
        elif intent == IntentType.MEMORY:
            if knowledge_ctx.get("chat_ctx"):
                prompt = (
                    f"Previous conversation:\n{knowledge_ctx['chat_ctx']}\n\n"
                    f"User now asks: {user_input}\n\n"
                    f"Answer using the conversation history above."
                )
            else:
                prompt = user_input
            return mgr.chat(prompt, history=chat_log)

        # ── FILE_SEARCH ───────────────────────────────────────────────────────
        elif intent == IntentType.FILE_SEARCH:
            # File reading is handled by commands.handle_command().
            # If we reach here, treat as a general chat about the file topic.
            return mgr.chat(user_input, history=chat_log)

        # ── CHAT (default) ───────────────────────────────────────────────────
        else:
            return mgr.chat(user_input, history=chat_log)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────────────────────────────────────

def _coding_prompt(user_input: str, ctx: dict) -> str:
    """Enrich a coding request with any available web context."""
    if ctx.get("web_data"):
        return (
            f"Reference material from web:\n{ctx['web_data']}\n\n"
            f"Task: {user_input}"
        )
    return user_input


def _research_prompt(user_input: str, ctx: dict, config) -> str:
    """Build a structured synthesis prompt for REASONING queries."""
    parts: list[str] = []
    if ctx.get("wiki_data"):
        parts.append(f"[Wikipedia Background]\n{ctx['wiki_data']}")
    if ctx.get("web_data"):
        parts.append(f"[Live Web Data]\n{ctx['web_data']}")

    if not parts:
        return user_input

    combined = "\n\n".join(parts)
    return (
        f"You are Jarvis, created by {config.DEVELOPER_ALIAS}. "
        f"Using ONLY the research data below, write a clear, well-structured answer. "
        f"Use numbered points or section headings where appropriate.\n\n"
        f"=== RESEARCH DATA ===\n{combined}\n\n"
        f"=== USER QUERY ===\n{user_input}\n\n"
        f"=== YOUR ANSWER ==="
    )
