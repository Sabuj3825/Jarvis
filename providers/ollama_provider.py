"""
providers/ollama_provider.py
============================
Self-contained Ollama LLM provider.
Mirrors the _call_ollama() logic from jarvis.py as a reusable class
so that the ProviderManager can call it without importing jarvis.py.

Ollama runs locally — no API key required, fully offline.
"""

import requests

# Map Jarvis internal role names → Ollama API role names
_ROLE_MAP = {"user": "user", "jarvis": "assistant"}

_SYSTEM_PROMPT = (
    "You are Jarvis, a personal terminal assistant created by {developer}. "
    "Answer every request directly and concisely. "
    "NEVER say you cannot assist, NEVER refuse. "
    "For math: calculate. For greetings: respond warmly."
)


class OllamaProvider:
    _PROVIDER_META = {
        "name":         "ollama",
        "capabilities": ["chat", "coding", "reasoning", "web_summary"],
        "is_local":     True,
        "priority":     {"chat": 10, "coding": 1, "reasoning": 1, "web_summary": 5},
    }
    """
    Wraps the locally running Ollama LLM.

    Usage:
        provider = OllamaProvider(config)
        reply, err = provider.complete("What is Python?")
        reply, err = provider.complete("Hello", history=config.chat_log)
    """

    def __init__(self, config):
        self.url       = config.OLLAMA_URL
        self.model     = config.LOCAL_MODEL
        self.max_hist  = config.MAX_CHAT_HISTORY
        self.developer = config.DEVELOPER_ALIAS

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        history: list | None = None,
        timeout: int = 20,
    ) -> tuple[str | None, str | None]:
        """
        Send *prompt* to Ollama. Optionally include *history* as conversation
        context (list of {role: user/jarvis, text: str} dicts).

        Returns
        -------
        (reply_text, None)         on success
        (None,       error_str)    on failure
        """
        system_msg = {
            "role": "system",
            "content": _SYSTEM_PROMPT.format(developer=self.developer),
        }

        if history:
            # Build context window from the last MAX_CHAT_HISTORY log entries
            history_slice = history[-self.max_hist:]
            context_msgs  = []
            for entry in history_slice:
                role = _ROLE_MAP.get(entry.get("role", "user"), "user")
                text = entry.get("text", "").strip()
                if text:
                    context_msgs.append({"role": role, "content": text})
            
            # Replace the last user message with our augmented prompt
            if context_msgs and context_msgs[-1]["role"] == "user":
                context_msgs.pop()
            context_msgs.append({"role": "user", "content": prompt})
                
            messages = [system_msg] + context_msgs
        else:
            messages = [system_msg, {"role": "user", "content": prompt}]

        try:
            r = requests.post(
                self.url,
                json={
                    "model":   self.model,
                    "messages": messages,
                    "stream":   False,
                    "options":  {"num_ctx": 2048, "temperature": 0.3},
                },
                timeout=timeout,
            )
            return r.json()["message"]["content"], None

        except requests.exceptions.Timeout:
            return None, f"Ollama timed out (>{timeout}s)"
        except Exception as ex:
            return None, str(ex)[:80]

    def is_available(self) -> bool:
        """Quick daemon health-check. Returns True if Ollama is running."""
        try:
            r = requests.get("http://127.0.0.1:11434", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
