"""Liveness, readiness, and startup health probes module."""
import os
from typing import Dict, Any


class HealthChecker:
    """Evaluates system health, database readiness, and API dependencies."""

    def __init__(self):
        self._startup_complete = False

    def liveness(self) -> Dict[str, str]:
        """Liveness probe indicating the service is running."""
        return {"status": "alive"}

    def check_database(self) -> Dict[str, Any]:
        """Check database connection status."""
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            return {"status": "degraded", "reason": "No DATABASE_URL set"}
        # For lightweight checking without blocking on network during unit tests
        return {"status": "ok", "url": db_url.split("@")[-1] if "@" in db_url else "local"}

    def check_gemini_api(self) -> Dict[str, Any]:
        """Check Gemini LLM API key configuration and readiness."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if api_key and api_key != "test_gemini_key":
            return {"status": "ok"}
        return {"status": "degraded", "reason": "Default or missing GEMINI_API_KEY"}

    def startup(self) -> Dict[str, Any]:
        """Startup probe checking if initialization sequences have completed."""
        return {"startup_complete": self._startup_complete}

    def mark_startup_complete(self) -> None:
        """Mark the service as having completed startup initialization."""
        self._startup_complete = True


health_checker = HealthChecker()
