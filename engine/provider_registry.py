"""
engine/provider_registry.py
============================
Plugin registry for AI providers.

Every AI provider self-registers by adding a `_PROVIDER_META` class variable
and calling `ProviderRegistry.register(instance)` — or by being discovered
automatically via `ProviderRegistry.discover(config)`.

Provider metadata schema
------------------------
    _PROVIDER_META = {
        "name":         str,                # unique key (e.g. "ollama")
        "capabilities": list[str],          # task types this provider handles
        "is_local":     bool,               # True = no internet required
        "priority":     int,                # higher = preferred when equal capability
        "models":       dict[str, list],    # optional {category: [model_ids]}
    }

The `capabilities` list uses the same strings as IntentType and task names:
    "chat", "coding", "reasoning", "vision", "web_summary"

Usage
-----
    from engine.provider_registry import ProviderRegistry

    # Discover + instantiate all providers
    ProviderRegistry.discover(config)

    # Get ordered providers for a task
    providers = ProviderRegistry.get_providers_for("coding")
"""

from __future__ import annotations

import importlib
import os
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class ProviderRegistry:
    """
    Central registry of all active AI providers.

    Providers are discovered from the `providers/` directory.
    Add a new provider by creating a new module with `_PROVIDER_META` — no
    changes to existing files required.
    """

    _providers: list[Any] = []   # list of provider instances

    @classmethod
    def register(cls, provider: Any) -> None:
        """Add a provider instance to the registry."""
        meta = getattr(provider, "_PROVIDER_META", {})
        name = meta.get("name", type(provider).__name__)
        for existing in cls._providers:
            e_meta = getattr(existing, "_PROVIDER_META", {})
            if e_meta.get("name") == name:
                return  # already registered
        cls._providers.append(provider)

    @classmethod
    def discover(cls, config) -> None:
        """
        Scan the `providers/` directory for modules containing classes with
        `_PROVIDER_META`, instantiate them, and register them.

        Falls back gracefully if any provider fails to import or instantiate.
        """
        base_dir      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        providers_dir = os.path.join(base_dir, "providers")

        if not os.path.isdir(providers_dir):
            return

        for filename in sorted(os.listdir(providers_dir)):
            if not filename.endswith("_provider.py"):
                continue
            module_name = filename[:-3]  # strip .py
            try:
                mod = importlib.import_module(f"providers.{module_name}")
            except Exception as ex:
                print(f"[ProviderRegistry]: Could not import providers.{module_name} — {ex}")
                continue

            # Find the first class with _PROVIDER_META in this module
            for attr_name in dir(mod):
                cls_obj = getattr(mod, attr_name, None)
                if (
                    isinstance(cls_obj, type)
                    and hasattr(cls_obj, "_PROVIDER_META")
                    and cls_obj._PROVIDER_META.get("name")
                ):
                    try:
                        instance = cls_obj(config)
                        cls.register(instance)
                    except Exception as ex:
                        print(f"[ProviderRegistry]: Could not instantiate {attr_name} — {ex}")
                    break  # one class per module

    @classmethod
    def get_providers_for(
        cls,
        capability: str,
        available_only: bool = True,
    ) -> list[Any]:
        """
        Return providers that support *capability*, ordered by:
        1. is_local (True first — Local-First policy)
        2. priority (higher first)

        Parameters
        ----------
        capability     : e.g. "chat", "coding", "reasoning", "vision"
        available_only : skip providers where is_available() == False
        """
        matching = []
        for p in cls._providers:
            meta = getattr(p, "_PROVIDER_META", {})
            if capability not in meta.get("capabilities", []):
                continue
            if available_only and hasattr(p, "is_available") and not p.is_available():
                continue
            matching.append(p)

        return sorted(
            matching,
            key=lambda p: (
                -int(getattr(p, "_PROVIDER_META", {}).get("is_local", False)),
                -getattr(p, "_PROVIDER_META", {}).get("priority", 0),
            ),
        )

    @classmethod
    def all_providers(cls) -> list[Any]:
        """Return all registered providers."""
        return list(cls._providers)

    @classmethod
    def reset(cls) -> None:
        """Clear registry (used in tests only)."""
        cls._providers = []
