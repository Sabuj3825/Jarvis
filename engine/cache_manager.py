"""
engine/cache_manager.py
=======================
Handles storing, retrieving, and expiring cached knowledge.
Extracted from jarvis.py to decouple storage logic from the main pipeline.
"""

from __future__ import annotations

import datetime
import os
import json
from routing.intent_detector import IntentType

def load_json_registry(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} if "knowledge" in file_path else []
    return {} if "knowledge" in file_path else []

def save_json_registry(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

class CacheManager:
    """
    Manages the knowledge cache.
    """

    def __init__(self, config):
        self.config = config
        self.cache_file = config.KNOWLEDGE_FILE

    def check_cache(self, query: str) -> dict | None:
        """
        Check if a valid, unexpired answer exists for the query.
        Returns the cache entry dict, or None if missed/expired.
        """
        knowledge_base = load_json_registry(self.cache_file)
        
        if query not in knowledge_base:
            return None
            
        entry = knowledge_base[query]
        expires_at = entry.get("expires_at")
        
        if expires_at:
            try:
                expiry_dt = datetime.datetime.strptime(expires_at, "%Y-%m-%d")
                if datetime.datetime.now() > expiry_dt:
                    # Expired, remove from cache
                    del knowledge_base[query]
                    save_json_registry(self.cache_file, knowledge_base)
                    return None
            except ValueError:
                pass # Malformed date, treat as valid

        return entry

    def write_cache(self, query: str, answer: str, intent: IntentType, confidence: str = "high") -> None:
        """
        Write a verified fact to the cache.
        """
        # Only cache certain intents
        cache_key = intent.to_cache_key()
        if cache_key == "conversation":
            return
            
        knowledge_base = load_json_registry(self.cache_file)
        
        # Calculate expiry (default 7 days for web data)
        expiry_dt = datetime.datetime.now() + datetime.timedelta(days=7)
        
        knowledge_base[query] = {
            "fact_extracted": answer,
            "source": cache_key,
            "confidence": confidence,
            "expires_at": expiry_dt.strftime("%Y-%m-%d")
        }
        
        save_json_registry(self.cache_file, knowledge_base)

    def wipe_cache(self, query: str) -> None:
        """
        Wipe a specific query from the cache (used when user says "wrong").
        """
        knowledge_base = load_json_registry(self.cache_file)
        if query in knowledge_base:
            del knowledge_base[query]
            save_json_registry(self.cache_file, knowledge_base)
