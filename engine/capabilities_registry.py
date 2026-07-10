"""
engine/capabilities_registry.py
===============================
Dynamically manages and loads JARVIS capabilities from config/capabilities.json.

This replaces the hardcoded list of local commands and AI capability strings.
"""

from __future__ import annotations

import json
import os
from typing import Any

class CapabilitiesRegistry:
    _local_commands: frozenset[str] = frozenset()
    _ai_capabilities: frozenset[str] = frozenset()
    _knowledge_sources: frozenset[str] = frozenset()

    @classmethod
    def load(cls) -> None:
        """Load capabilities from config/capabilities.json."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cap_file = os.path.join(base_dir, "config", "capabilities.json")
        
        if not os.path.exists(cap_file):
            print(f"⚠️ [CapabilitiesRegistry]: {cap_file} missing. Using defaults.")
            cls._local_commands = frozenset(["battery", "weather", "time", "date"])
            cls._ai_capabilities = frozenset(["chat", "coding", "reasoning", "vision", "web_summary"])
            cls._knowledge_sources = frozenset(["web", "wikipedia", "chat_history"])
            return

        try:
            with open(cap_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            cls._local_commands = frozenset(data.get("local_commands", []))
            cls._ai_capabilities = frozenset(data.get("ai_capabilities", []))
            cls._knowledge_sources = frozenset(data.get("knowledge_sources", []))
        except Exception as e:
            print(f"⚠️ [CapabilitiesRegistry]: Failed to parse capabilities.json: {e}")

    @classmethod
    def get_local_commands(cls) -> frozenset[str]:
        if not cls._local_commands:
            cls.load()
        return cls._local_commands

    @classmethod
    def get_ai_capabilities(cls) -> frozenset[str]:
        if not cls._ai_capabilities:
            cls.load()
        return cls._ai_capabilities

    @classmethod
    def get_knowledge_sources(cls) -> frozenset[str]:
        if not cls._knowledge_sources:
            cls.load()
        return cls._knowledge_sources
