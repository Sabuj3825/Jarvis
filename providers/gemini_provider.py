"""
providers/gemini_provider.py
=============================
Self-contained Gemini REST API provider with integrated rate guard.
Mirrors and encapsulates the gemini_safe_request() logic from jarvis.py
so the ProviderManager can use it without importing jarvis.py.

Free-tier limits respected:
  - Max 14 calls/minute (safety margin below the 15 RPM limit)
  - Min 4.3 s gap between consecutive calls
  - Auto-retry once with 62 s backoff if a 429 slips through
"""

import json
import time
import requests


class GeminiProvider:
    # ── Plugin metadata — auto-discovered by engine/provider_registry.py ──────
    _PROVIDER_META = {
        "name":         "gemini",
        "capabilities": ["chat", "coding", "reasoning", "vision", "web_summary"],
        "is_local":     False,
        "priority":     5,   # cloud fallback
    }
    """
    Wraps the Gemini REST API with built-in rate guard.

    Usage:
        provider = GeminiProvider(config)
        reply, err = provider.complete("What is Python?")
        reply, err = provider.complete("Summarize: ...", system_prefix="You are Jarvis...")

        # For callers that need raw Response access (e.g. react_agent):
        res = provider.raw_request(payload_dict)
    """

    _RPM_SAFE = 14    # stay under the 15 RPM free-tier limit
    _MIN_GAP  = 4.3   # minimum seconds between consecutive calls

    def __init__(self, config):
        self.url       = config.URL
        self.headers   = config.HEADERS
        self.api_key   = config.API_KEY
        self.developer = config.DEVELOPER_ALIAS
        self._call_log: list[float] = []   # timestamps of recent calls

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Return True if a real API key has been set."""
        return bool(self.api_key) and "YOUR_GEMINI" not in self.api_key

    def complete(
        self,
        prompt: str,
        system_prefix: str | None = None,
    ) -> tuple[str | None, str | None]:
        """
        Send *prompt* to Gemini. An optional *system_prefix* is prepended to
        give Jarvis its persona without a separate system-role message
        (Gemini REST API doesn't support a dedicated system role natively).

        Returns
        -------
        (reply_text, None)         on success
        (None,       error_str)    on failure
        """
        if not self.is_configured():
            return None, "Gemini API key not configured"

        full_prompt = f"{system_prefix}\n\n{prompt}" if system_prefix else prompt

        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}]
        }

        try:
            res = self._rate_guarded_post(payload)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return text, None
            if res.status_code == 429:
                return None, "Gemini rate limit (429) — retry later"
            return None, f"Gemini HTTP {res.status_code}"

        except requests.exceptions.Timeout:
            return None, "Gemini timed out (>20 s)"
        except Exception as ex:
            return None, str(ex)[:80]

    def raw_request(self, payload: dict) -> requests.Response:
        """
        Exposes the rate-guarded POST for callers that build their own payloads
        (react_agent still injects its own Gemini payloads directly).
        """
        return self._rate_guarded_post(payload)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _rate_guarded_post(self, payload: dict) -> requests.Response:
        """Apply rate guard, then POST. Auto-retries once on 429."""
        self._enforce_rate_limit()
        res = requests.post(
            self.url,
            headers=self.headers,
            data=json.dumps(payload),
            timeout=20,
        )
        self._call_log.append(time.time())

        # Auto-retry once if a 429 slipped through timing gaps
        if res.status_code == 429:
            retry_wait = 62
            print(f"[Gemini Rate Guard]: Got 429. Retrying in {retry_wait}s...")
            for remaining in range(retry_wait, 0, -1):
                print(f"   ⏱  Retry in {remaining}s...", end="\r")
                time.sleep(1)
            print("")
            res = requests.post(
                self.url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=20,
            )
            self._call_log.append(time.time())

        return res

    def _enforce_rate_limit(self) -> None:
        """Block until it is safe to make another Gemini call."""
        now = time.time()

        # Prune timestamps older than 60 s
        self._call_log = [t for t in self._call_log if now - t < 60]

        if len(self._call_log) >= self._RPM_SAFE:
            # Near per-minute limit → wait until the oldest call is >60 s old
            oldest   = self._call_log[0]
            wait_sec = 60.0 - (now - oldest) + 1.0
            if wait_sec > 0:
                print(f"[Gemini Rate Guard]: {len(self._call_log)} RPM limit reached. Waiting {wait_sec:.0f}s...")
                for remaining in range(int(wait_sec), 0, -1):
                    print(f"   ⏱  {remaining}s remaining...", end="\r")
                    time.sleep(1)
                print("")

        elif self._call_log:
            # Enforce minimum gap between consecutive calls
            elapsed = now - self._call_log[-1]
            if elapsed < self._MIN_GAP:
                time.sleep(self._MIN_GAP - elapsed)
