#!/usr/bin/env python3
"""
update_openrouter_models.py
============================
Automatically discovers, tests, and caches ONLY working OpenRouter models
for the JARVIS AI project.

Categories tested: Chat · Reasoning · Vision

Author  : JARVIS Project
Python  : 3.10+
License : MIT
"""

# ─────────────────────────────────────────────────────────────────────────────
# Standard-library imports (no extra installs required for these)
# ─────────────────────────────────────────────────────────────────────────────
import csv
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Third-party imports
# ─────────────────────────────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    print("Missing dependency: requests\n   Install with: pip install requests")
    sys.exit(1)

try:
    from openai import OpenAI  # openrouter SDK re-exports OpenAI client
except ImportError:
    try:
        import openai
        from openai import OpenAI
    except ImportError:
        print(
            "Missing dependency: openai (or openrouter)\n"
            "   Install with: pip install openai\n"
            "   Or:           pip install openrouter"
        )
        sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# OpenRouter catalog endpoint - always fetches the newest list
OPENROUTER_CATALOG_URL: str = "https://openrouter.ai/api/v1/models"

# Output file paths (relative to this script's directory)
_SCRIPT_DIR = Path(__file__).resolve().parent
CSV_REPORT_PATH: Path = _SCRIPT_DIR / "openrouter_model_report.csv"
JSON_CACHE_PATH: Path = _SCRIPT_DIR / "openrouter_models.json"

# Tiny test prompt - cheap and fast
TEST_PROMPT: str = "Reply with only the word OK."

# How many models to test in parallel (keep low to respect rate limits)
MAX_WORKERS: int = 5

# Per-model request timeout in seconds
REQUEST_TIMEOUT: int = 30

# Valid target categories
CATEGORIES = ("chat", "reasoning", "vision")

# ─────────────────────────────────────────────────────────────────────────────
# Keyword heuristics (ONLY used when metadata is insufficient)
# ─────────────────────────────────────────────────────────────────────────────

# Models / families that signal a "reasoning" specialisation
_REASONING_KEYWORDS = frozenset(
    [
        "o1", "o3", "o4", "deepseek-r", "deepseek-r1", "qwq", "skywork-or",
        "reasoning", "think", "thinker", "reflection", "r1", "r7b",
        "prover", "nemotron-super", "lfm-7b-reasoning",
    ]
)

# Models / families that indicate vision capability
_VISION_KEYWORDS = frozenset(
    [
        "vision", "vl", "-vl-", "llava", "pixtral", "gemini-pro-vision",
        "gpt-4-vision", "gpt-4v", "claude-3", "claude-3.5", "claude-3-7",
        "claude-4", "phi-vision", "phi-3-vision", "minicpm-v",
        "internvl", "qwen-vl", "cogvlm", "idefics", "fuyu",
        "bakllava", "moondream", "florence",
    ]
)

# Modality strings that definitively indicate vision input support
_VISION_MODALITIES = frozenset(["image", "file"])

# Categories that we explicitly EXCLUDE from testing
_EXCLUDED_CAPABILITY_TYPES = frozenset(
    [
        "embedding", "reranking", "stt", "tts",
        "image-generation", "video-generation",
        "moderation", "guardrails",
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
# Console helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print(msg: str = "") -> None:
    """Print a message and flush stdout immediately (important on Windows)."""
    print(msg, flush=True)


def _separator(char: str = "-", width: int = 44) -> str:
    return char * width


# ─────────────────────────────────────────────────────────────────────────────
# API key helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """
    Retrieve the OpenRouter API key from the environment.
    Falls back to a jarvis-specific env var, then prompts the user.
    """
    for env_var in ("OPENROUTER_API_KEY", "JARVIS_OPENROUTER_KEY", "OR_API_KEY"):
        key = os.environ.get(env_var, "").strip()
        if key:
            return key

    # Last resort: interactive prompt (works in terminal; skipped in CI)
    try:
        key = input("Enter your OpenRouter API key: ").strip()
        if key:
            return key
    except (EOFError, KeyboardInterrupt):
        pass

    _print("No OpenRouter API key found.")
    _print("   Set the environment variable OPENROUTER_API_KEY and re-run.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 - Download model catalog
# ─────────────────────────────────────────────────────────────────────────────

def download_model_catalog(api_key: str) -> list[dict[str, Any]]:
    """
    Fetch the full model list from OpenRouter.
    Returns the raw list of model dicts from the API response.
    Raises RuntimeError if the request fails.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/jarvis-ai",
        "X-Title": "JARVIS Model Updater",
    }
    try:
        resp = requests.get(
            OPENROUTER_CATALOG_URL,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        models: list[dict[str, Any]] = data.get("data", [])
        if not models:
            raise RuntimeError("API returned an empty model list.")
        return models
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Failed to download model catalog: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 - Classify models
# ─────────────────────────────────────────────────────────────────────────────

def _is_excluded(model: dict[str, Any]) -> bool:
    """
    Return True if the model belongs to a category we never want to test
    (embeddings, TTS, image-gen, etc.).
    """
    model_id: str = model.get("id", "").lower()
    description: str = (model.get("description") or "").lower()
    architecture: dict = model.get("architecture", {}) or {}
    input_modalities: list[str] = architecture.get("input_modalities", []) or []
    output_modalities: list[str] = architecture.get("output_modalities", []) or []
    tokenizer: str = (architecture.get("tokenizer") or "").lower()

    # Explicit capability type field (most reliable)
    capability: str = (
        model.get("capability")
        or model.get("type")
        or model.get("modality")
        or ""
    ).lower()
    if any(excl in capability for excl in _EXCLUDED_CAPABILITY_TYPES):
        return True

    # Output modalities can expose non-chat models
    non_text_outputs = {"image", "audio", "video", "embedding"}
    if set(output_modalities) & non_text_outputs:
        return True

    # Tokenizer hint
    if tokenizer in ("clip", "whisper", "dall-e"):
        return True

    # Keyword exclusions in model ID / description
    exclusion_keywords = [
        "embed", "rerank", "whisper", "dall-e", "stable-diffusion",
        "tts", "stt", "speech", "transcri", "image-gen", "video-gen",
        "moderat", "guardrail",
    ]
    combined = model_id + " " + description
    if any(kw in combined for kw in exclusion_keywords):
        return True

    return False


def _classify_model(model: dict[str, Any]) -> Optional[str]:
    """
    Classify a single model as 'chat', 'reasoning', or 'vision'.
    Returns None if the model should be excluded entirely.

    Priority:
      1. Explicit capability / modality metadata from the API
      2. Input modality list
      3. Keyword heuristics (fallback only)
    """
    if _is_excluded(model):
        return None

    model_id: str = model.get("id", "").lower()
    description: str = (model.get("description") or "").lower()
    architecture: dict = model.get("architecture", {}) or {}
    input_modalities: list[str] = [
        m.lower() for m in (architecture.get("input_modalities") or [])
    ]

    # 1. Capability metadata (most reliable)
    capability: str = (
        model.get("capability")
        or model.get("type")
        or model.get("modality")
        or ""
    ).lower()

    if "reasoning" in capability:
        return "reasoning"
    if "vision" in capability or "multimodal" in capability:
        return "vision"
    if "chat" in capability or "text" in capability:
        # Still check input modalities before declaring pure chat
        pass  # fall through to modality check below

    # 2. Input modality list
    if _VISION_MODALITIES & set(input_modalities):
        # Models that accept images / files are Vision models
        return "vision"

    # 3. Keyword heuristics (fallback)
    combined_text = model_id + " " + description

    # Check reasoning keywords first (more specific)
    if any(kw in combined_text for kw in _REASONING_KEYWORDS):
        return "reasoning"

    # Check vision keywords
    if any(kw in combined_text for kw in _VISION_KEYWORDS):
        return "vision"

    # Default: treat as chat if it passed the exclusion filter
    return "chat"


def classify_all_models(
    raw_models: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Classify all downloaded models into chat / reasoning / vision buckets.
    Returns a dict: { "chat": [...], "reasoning": [...], "vision": [...] }
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        "chat": [],
        "reasoning": [],
        "vision": [],
    }

    for model in raw_models:
        category = _classify_model(model)
        if category is not None:
            buckets[category].append(model)

    return buckets


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 - Test a single model
# ─────────────────────────────────────────────────────────────────────────────

def test_model(
    client: OpenAI,
    model: dict[str, Any],
    category: str,
) -> dict[str, Any]:
    """
    Send a tiny test prompt to *model* via the OpenRouter API.
    Returns a result dict regardless of success or failure.
    """
    model_id: str = model.get("id", "unknown")
    result: dict[str, Any] = {
        "category": category,
        "model": model_id,
        "success": False,
        "latency": None,
        "model_used": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cost": None,
        "error": None,
    }

    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_tokens=10,
            timeout=REQUEST_TIMEOUT,
        )

        elapsed = time.perf_counter() - start
        result["latency"] = round(elapsed, 3)
        result["success"] = True
        result["model_used"] = getattr(response, "model", model_id)

        # Token usage
        usage = getattr(response, "usage", None)
        if usage:
            result["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
            result["completion_tokens"] = getattr(usage, "completion_tokens", None)
            result["total_tokens"] = getattr(usage, "total_tokens", None)

        # Cost (OpenRouter-specific field)
        # The cost is sometimes surfaced in usage or in a custom attribute
        cost_val = None
        if hasattr(usage, "cost"):
            cost_val = usage.cost  # type: ignore[attr-defined]
        elif hasattr(response, "cost"):
            cost_val = response.cost  # type: ignore[attr-defined]
        result["cost"] = cost_val

    except Exception as exc:  # noqa: BLE001 - intentionally broad
        elapsed = time.perf_counter() - start
        result["latency"] = round(elapsed, 3)
        # Capture a concise error message
        result["error"] = _sanitise_error(exc)

    return result


def _sanitise_error(exc: Exception) -> str:
    """
    Return a short, human-readable error string from any exception.
    Avoids leaking API keys or overly long tracebacks.
    """
    msg = str(exc)
    # Truncate very long messages
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return type(exc).__name__ + ": " + msg


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 - Test all models in a category concurrently
# ─────────────────────────────────────────────────────────────────────────────

def test_category(
    client: OpenAI,
    category: str,
    models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Test all *models* for the given *category* using a thread pool.
    Returns a list of result dicts (one per model).
    """
    total = len(models)
    _print(f"\n Testing {category.capitalize()} models ({total})...")

    results: list[dict[str, Any]] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_model = {
            executor.submit(test_model, client, m, category): m
            for m in models
        }

        for future in as_completed(future_to_model):
            completed += 1
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                # This should never happen because test_model already catches
                # all exceptions, but we guard defensively.
                model_id = future_to_model[future].get("id", "unknown")
                result = {
                    "category": category,
                    "model": model_id,
                    "success": False,
                    "latency": None,
                    "model_used": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "cost": None,
                    "error": _sanitise_error(exc),
                }

            results.append(result)
            _print_model_result(result, completed, total)

    return results


def _print_model_result(result: dict[str, Any], idx: int, total: int) -> None:
    """Print a single-line progress indicator for a tested model."""
    icon = "+" if result["success"] else "x"
    model_id = result["model"]
    # Pad index for alignment
    idx_str = str(idx).rjust(len(str(total)))

    if result["success"]:
        latency_str = f"  [{result['latency']}s]"
        _print(f"  {icon} [{idx_str}/{total}] {model_id}{latency_str}")
    else:
        err_short = (result.get("error") or "Unknown error")[:60]
        _print(f"  {icon} [{idx_str}/{total}] {model_id}  <- {err_short}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 - Save CSV report
# ─────────────────────────────────────────────────────────────────────────────

def save_csv_report(all_results: list[dict[str, Any]], path: Path) -> None:
    """
    Write every tested model (successes AND failures) to a CSV file.
    """
    fieldnames = [
        "Category",
        "Model",
        "Success",
        "Latency",
        "Prompt Tokens",
        "Completion Tokens",
        "Total Tokens",
        "Cost",
        "Error",
    ]

    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            writer.writerow(
                {
                    "Category": r.get("category", ""),
                    "Model": r.get("model", ""),
                    "Success": r.get("success", False),
                    "Latency": r.get("latency", ""),
                    "Prompt Tokens": r.get("prompt_tokens", ""),
                    "Completion Tokens": r.get("completion_tokens", ""),
                    "Total Tokens": r.get("total_tokens", ""),
                    "Cost": r.get("cost", ""),
                    "Error": r.get("error", ""),
                }
            )


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 - Save JSON cache
# ─────────────────────────────────────────────────────────────────────────────

def save_json_cache(
    all_results: list[dict[str, Any]],
    path: Path,
) -> None:
    """
    Write the JSON cache containing ONLY successfully tested models.
    The cache is grouped by category and includes rich metadata.
    """
    cache: dict[str, Any] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "chat": [],
        "reasoning": [],
        "vision": [],
    }

    for r in all_results:
        if not r.get("success"):
            continue
        category: str = r.get("category", "chat")
        if category not in cache:
            cache[category] = []

        entry: dict[str, Any] = {
            "model": r["model"],
            "latency": r.get("latency"),
            "prompt_tokens": r.get("prompt_tokens"),
            "completion_tokens": r.get("completion_tokens"),
            "total_tokens": r.get("total_tokens"),
            "cost": r.get("cost"),
        }
        cache[category].append(entry)

    # Sort each category alphabetically for deterministic output
    for cat in CATEGORIES:
        cache[cat].sort(key=lambda x: x["model"])

    with path.open("w", encoding="utf-8") as fp:
        json.dump(cache, fp, indent=4, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 - Print final summary
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(
    all_results: list[dict[str, Any]],
    elapsed: float,
) -> None:
    """Print the final summary table to stdout."""
    counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    total_failed = 0

    for r in all_results:
        if r.get("success"):
            cat = r.get("category", "")
            if cat in counts:
                counts[cat] += 1
        else:
            total_failed += 1

    total_working = sum(counts.values())

    sep = _separator()
    _print(f"\nUpdate Summary")
    _print(sep)
    _print(f"Chat Models      : {counts['chat']}")
    _print(f"Reasoning Models : {counts['reasoning']}")
    _print(f"Vision Models    : {counts['vision']}")
    _print("")
    _print(f"Total Working    : {total_working}")
    _print(f"Failed           : {total_failed}")
    _print("")
    _print(f"CSV Report       : {CSV_REPORT_PATH.name}")
    _print(f"Cache File       : {JSON_CACHE_PATH.name}")
    _print(sep)
    _print(f"\nUpdate completed in {elapsed:.1f} seconds.")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    script_start = time.perf_counter()

    _print("Updating OpenRouter AI Models...\n")

    # Retrieve API key
    api_key = get_api_key()

    # Build OpenAI-compatible client pointed at OpenRouter
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/jarvis-ai",
            "X-Title": "JARVIS Model Updater",
        },
    )

    # Step 1: Download catalog
    _print("Downloading latest model catalog...")
    try:
        raw_models = download_model_catalog(api_key)
    except RuntimeError as exc:
        _print(f"Error: {exc}")
        sys.exit(1)

    _print(f"{len(raw_models)} models found")

    # Step 2: Classify models
    buckets = classify_all_models(raw_models)

    excluded_count = len(raw_models) - sum(len(v) for v in buckets.values())
    _print(
        f"Classified -> "
        f"Chat: {len(buckets['chat'])}  "
        f"Reasoning: {len(buckets['reasoning'])}  "
        f"Vision: {len(buckets['vision'])}  "
        f"(Excluded: {excluded_count})"
    )

    # Step 3: Test all models
    all_results: list[dict[str, Any]] = []

    for category in CATEGORIES:
        models_in_cat = buckets[category]
        if not models_in_cat:
            _print(f"\nNo {category.capitalize()} models found - skipping.")
            continue
        results = test_category(client, category, models_in_cat)
        all_results.extend(results)

    # Step 4: Report on failures / additions
    failed_results = [r for r in all_results if not r["success"]]
    working_results = [r for r in all_results if r["success"]]

    _print(f"\nRemoving unavailable failed models... ({len(failed_results)} removed)")
    _print(f"Adding newly working models...         ({len(working_results)} added)")

    # Step 5: Save outputs
    _print("\nSaving model cache...")

    try:
        save_csv_report(all_results, CSV_REPORT_PATH)
        _print(f"   CSV report saved -> {CSV_REPORT_PATH}")
    except OSError as exc:
        _print(f"   Could not save CSV report: {exc}")

    try:
        save_json_cache(all_results, JSON_CACHE_PATH)
        _print(f"   JSON cache saved -> {JSON_CACHE_PATH}")
    except OSError as exc:
        _print(f"   Could not save JSON cache: {exc}")

    # Step 6: Final summary
    total_elapsed = time.perf_counter() - script_start
    print_summary(all_results, total_elapsed)


# ─────────────────────────────────────────────────────────────────────────────
# Guard
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _print("\nInterrupted by user. Partial results may have been saved.")
        sys.exit(130)
    except Exception:  # noqa: BLE001
        _print("\nUnexpected fatal error:")
        traceback.print_exc()
        sys.exit(1)
