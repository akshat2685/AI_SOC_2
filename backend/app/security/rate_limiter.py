"""Role-aware rate limiting module."""
import time
from typing import Dict, Tuple, List


class RoleAwareRateLimiter:
    """Rate limiter that scales request limits based on user role and endpoint."""

    BASE_LIMITS: Dict[str, int] = {
        "/api/auth/login": 5,
        "/api/alerts": 60,
        "/api/incidents": 30,
        "default": 100,
    }

    ROLE_MULTIPLIERS: Dict[str, int] = {
        "admin": 3,
        "soc_manager": 2,
        "manager": 2,
        "soc_analyst": 1,
        "analyst": 1,
        "default": 1,
    }

    def __init__(self):
        # Key: (user_id, endpoint), Value: list of timestamps
        self._requests: Dict[Tuple[str, str], List[float]] = {}
        # Key: user_id, Value: blocked until timestamp
        self._blocked_users: Dict[str, float] = {}

    def block_user(self, user_id: str, duration_seconds: int = 300) -> None:
        """Block a user from making requests for a specified duration."""
        self._blocked_users[user_id] = time.time() + duration_seconds

    def check(self, user_id: str, role: str, endpoint: str) -> Tuple[bool, Dict[str, str]]:
        """Check if a request is permitted within rate limits."""
        now = time.time()

        # Check if blocked
        if user_id in self._blocked_users:
            if now < self._blocked_users[user_id]:
                return False, {
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(int(self._blocked_users[user_id] - now)),
                }
            else:
                del self._blocked_users[user_id]

        base_limit = self.BASE_LIMITS.get(endpoint, self.BASE_LIMITS["default"])
        multiplier = self.ROLE_MULTIPLIERS.get(role.lower(), self.ROLE_MULTIPLIERS["default"])
        max_requests = base_limit * multiplier

        key = (user_id, endpoint)
        if key not in self._requests:
            self._requests[key] = []

        # Prune requests older than 60 seconds (1 minute window)
        window_start = now - 60.0
        self._requests[key] = [ts for ts in self._requests[key] if ts >= window_start]

        current_count = len(self._requests[key])
        remaining = max(0, max_requests - current_count)

        if current_count >= max_requests:
            return False, {
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            }

        self._requests[key].append(now)
        remaining = max(0, max_requests - len(self._requests[key]))
        return True, {
            "X-RateLimit-Limit": str(max_requests),
            "X-RateLimit-Remaining": str(remaining),
        }
