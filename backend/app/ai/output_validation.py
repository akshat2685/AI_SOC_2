"""LLM output validation, HTML sanitization, and command safety verification module."""
import re
from typing import List, Tuple, Optional
import yaml


class OutputValidator:
    """Validates and sanitizes generative AI outputs before presentation or execution."""

    DANGEROUS_COMMANDS = [
        re.compile(r"\brm\s+-[rRfF]+\b", re.IGNORECASE),
        re.compile(r"\bformat\s+[c-z]:", re.IGNORECASE),
        re.compile(r"\bmkfs\b", re.IGNORECASE),
        re.compile(r"\bdd\s+if=", re.IGNORECASE),
        re.compile(r":\(\)\{\s*:\|\:&\s*\};:", re.IGNORECASE),  # fork bomb
        re.compile(r"\bchmod\s+-R\s+777\s+/", re.IGNORECASE),
    ]

    HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
    SCRIPT_TAG_PATTERN = re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL)

    def validate_incident_summary(self, summary: str) -> Tuple[bool, str]:
        """Validate an AI-generated incident summary."""
        if not summary or not isinstance(summary, str):
            return False, "Summary is empty or invalid"
        if len(summary) < 10:
            return False, "Summary is too short"
        return True, "Summary valid"

    def validate_remediation_steps(self, steps: List[str]) -> Tuple[bool, str]:
        """Validate AI-recommended remediation commands for destructive patterns."""
        if not isinstance(steps, list):
            return False, "Steps must be a list of strings"
        
        for step in steps:
            if not isinstance(step, str):
                return False, "Each step must be a string"
            for pattern in self.DANGEROUS_COMMANDS:
                if pattern.search(step):
                    return False, f"Step contains dangerous command pattern: '{step}'"
                    
        return True, "Remediation steps safe"

    def sanitize_summary(self, text: str) -> str:
        """Strip HTML tags and scripts from AI text summaries."""
        if not text or not isinstance(text, str):
            return ""
        # First remove script blocks completely
        cleaned = self.SCRIPT_TAG_PATTERN.sub("", text)
        # Then strip remaining HTML tags
        cleaned = self.HTML_TAG_PATTERN.sub("", cleaned)
        return cleaned.strip()

    def validate_detection_rule(self, rule: str, format: str = "sigma") -> Tuple[bool, str]:
        """Validate YAML/Sigma syntax structure for AI-generated detection rules."""
        if format.lower() == "sigma":
            try:
                data = yaml.safe_load(rule)
                if not isinstance(data, dict):
                    return False, "Sigma rule must parse to a YAML dictionary"
                required_keys = ["title", "logsource", "detection"]
                for key in required_keys:
                    if key not in data:
                        return False, f"Missing required Sigma rule section: '{key}'"
                return True, "Valid Sigma rule"
            except Exception as e:
                return False, f"YAML syntax error: {str(e)}"
        return True, "Unsupported format skipped"


output_validator = OutputValidator()
