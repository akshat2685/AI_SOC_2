"""Circuit breaker resilience module."""
import time
from enum import Enum
from typing import Callable, Any, Dict


class CircuitState(Enum):
    """Enumeration of circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """Implements the circuit breaker pattern to protect against cascading failures."""

    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0

    @property
    def state(self) -> CircuitState:
        """Get the current circuit breaker state, checking for recovery timeouts."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def call_sync(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a synchronous function wrapped in circuit breaker protection."""
        current_state = self.state
        if current_state == CircuitState.OPEN:
            raise CircuitBreakerError(f"CircuitBreaker '{self.name}' is OPEN. Fast-failing request.")

        self._total_calls += 1
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self) -> None:
        self._total_successes += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def _on_failure(self) -> None:
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN

    def get_metrics(self) -> Dict[str, Any]:
        """Retrieve telemetry and operational metrics for this circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self._total_calls,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "failure_count": self._failure_count,
        }
