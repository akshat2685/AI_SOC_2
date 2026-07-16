import re
import logging

logger = logging.getLogger(__name__)

class SecuritySanitizer:
    """Security sanitization logic for Prompt Injection Protection."""
    
    PROMPT_INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now", re.IGNORECASE),
        re.compile(r"bypass\s+rules", re.IGNORECASE),
        re.compile(r"system\s+prompt", re.IGNORECASE),
        re.compile(r"forget\s+everything", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_input(cls, user_input: str) -> str:
        """Sanitizes user input to prevent prompt injections."""
        sanitized = user_input
        for pattern in cls.PROMPT_INJECTION_PATTERNS:
            if pattern.search(sanitized):
                logger.warning(f"Prompt injection pattern detected: {pattern.pattern}")
                sanitized = pattern.sub("[REDACTED_PROMPT_INJECTION]", sanitized)
        return sanitized
