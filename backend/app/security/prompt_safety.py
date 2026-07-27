"""Prompt injection defense and LLM prompt safety module."""
import re
from typing import Tuple


class PromptSafetyEngine:
    """Defends LLM interactions against prompt injection and jailbreaks."""

    INJECTION_KEYWORDS = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
        re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
        re.compile(r"tell\s+me\s+secrets", re.IGNORECASE),
        re.compile(r"print\s+system\s+instructions", re.IGNORECASE),
    ]

    def check_input(self, text: str) -> Tuple[bool, str]:
        """Check user input or alert text for prompt injection attempts."""
        if not text or not isinstance(text, str):
            return True, "Safe"
        
        for pattern in self.INJECTION_KEYWORDS:
            if pattern.search(text):
                return False, f"Prompt injection detected: matched {pattern.pattern}"
                
        return True, "Safe"

    def sanitize_for_llm(self, text: str) -> str:
        """Sanitize user text and wrap with safety boundary instructions."""
        is_safe, reason = self.check_input(text)
        if not is_safe:
            # Strip dangerous phrases or replace
            cleaned = text
            for pattern in self.INJECTION_KEYWORDS:
                cleaned = pattern.sub("[FILTERED_PROMPT_INJECTION]", cleaned)
        else:
            cleaned = text
            
        return f"""=== CRITICAL SAFETY RULES ===
1. Do not execute system commands or disclose secrets.
2. Rely only on verified security data.
=== USER/ALERT INPUT ===
{cleaned}
=== END INPUT ==="""


prompt_safety = PromptSafetyEngine()
