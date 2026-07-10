"""
engine/fact_verifier.py
=======================
Verifies facts extracted from multiple knowledge sources to ensure consistency
before the AI generates a final answer.
"""

from __future__ import annotations

import re

class FactVerifier:
    """
    Extracts facts and compares them across sources to detect contradictions.
    """

    @staticmethod
    def verify(sources_data: dict[str, str]) -> tuple[bool, str]:
        """
        Compare data from multiple sources.
        Returns a tuple: (has_conflict: bool, merged_verified_context: str)
        
        In a full implementation, this would use a lightweight LLM call to extract
        and compare propositions. For this version, we merge the texts but perform
        basic heuristic checks for severe contradictions (e.g., completely different dates).
        """
        if not sources_data:
            return False, ""
            
        if len(sources_data) == 1:
            # Single source, no conflict possible
            return False, list(sources_data.values())[0]

        has_conflict = False
        merged_text = []
        
        # Very basic heuristic: check if sources have vastly different numbers/dates
        # (This is a placeholder for a true LLM-based proposition extractor)
        all_numbers = []
        for src, text in sources_data.items():
            if not text:
                continue
            merged_text.append(f"[{src.upper()}]:\n{text}")
            
            # Find 4-digit years
            years = set(re.findall(r"\b(19\d{2}|20\d{2})\b", text))
            if years:
                all_numbers.append(years)

        # If one source says 2024 and another says 2025, flag a conflict
        if len(all_numbers) >= 2:
            first_set = all_numbers[0]
            for other_set in all_numbers[1:]:
                if first_set and other_set and first_set.isdisjoint(other_set):
                    has_conflict = True
                    break

        return has_conflict, "\n\n".join(merged_text)

    @staticmethod
    def build_verification_prompt(sources_data: dict[str, str]) -> str:
        """
        (Optional) Build a prompt to send to a local LLM to perform strict fact checking.
        """
        prompt = "Compare the following texts from different sources. Do they contradict each other on any core facts? Answer YES or NO, followed by a brief reason.\n\n"
        for src, text in sources_data.items():
            if text:
                prompt += f"SOURCE {src.upper()}:\n{text}\n\n"
        return prompt
