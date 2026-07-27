"""Input validation and injection defense module."""
import re
from typing import Dict, Any, Tuple, Optional


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


# Common injection attack patterns (SQLi, XSS, Command Injection)
INJECTION_PATTERNS = [
    re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<.*?on\w+.*?=>", re.IGNORECASE),
    re.compile(r";\s*DROP\s+TABLE\s+", re.IGNORECASE),
    re.compile(r";\s*DELETE\s+FROM\s+", re.IGNORECASE),
    re.compile(r"UNION\s+ALL\s+SELECT", re.IGNORECASE),
    re.compile(r"(\%27)|(\')|(\-\-)|(\%23)|(#)", re.IGNORECASE),
]

# Refined SQLi check specifically for destructive commands
SQLI_DESTRUCTIVE = re.compile(r"(\b(DROP|DELETE|TRUNCATE|ALTER|EXEC|UNION)\b.*?(TABLE|FROM|DATABASE|SELECT))|(;\s*--)", re.IGNORECASE)
XSS_PATTERN = re.compile(r"(<script|javascript:|on\w+\s*=)", re.IGNORECASE)


def check_for_injection(text: str) -> Tuple[bool, str]:
    """Check a text string for SQL injection or XSS patterns."""
    if not isinstance(text, str):
        return True, "Safe"
    
    if XSS_PATTERN.search(text):
        return False, "XSS pattern detected"
    
    if SQLI_DESTRUCTIVE.search(text):
        return False, "SQL injection pattern detected"
        
    return True, "Safe"


class AlertIngestionValidator:
    """Validates incoming alert payloads against injection and schema requirements."""

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an alert payload dictionary."""
        if not isinstance(data, dict):
            raise ValidationError("Payload must be a dictionary")
        
        required_fields = ["source_system", "severity", "title"]
        for field in required_fields:
            if field not in data:
                raise ValidationError(f"Missing required field: {field}")
        
        # Check all string values for injection
        for key, value in data.items():
            if isinstance(value, str):
                is_safe, reason = check_for_injection(value)
                if not is_safe:
                    raise ValidationError(f"Field '{key}' failed validation: {reason}")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        is_safe, reason = check_for_injection(item)
                        if not is_safe:
                            raise ValidationError(f"List item in '{key}' failed validation: {reason}")
                            
        return data
