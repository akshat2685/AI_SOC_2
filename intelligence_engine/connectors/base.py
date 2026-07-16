"""Base connector with standardized abstract interface and SecurityEvent schema."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEvent(BaseModel):
    """Canonical event model that ALL connectors normalize into."""
    event_id: str
    tenant_id: str
    source: str
    event_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    timestamp: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_payload: dict[str, Any] = Field(default_factory=dict)
    iocs: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    topic: str | None = None


class BaseConnector(ABC):
    """Abstract base for all security-tool connectors.

    Every concrete connector must implement these 7 lifecycle methods
    so the intelligence engine can treat every data source uniformly.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish the underlying transport (TCP, HTTP session, etc.)."""
        ...

    @abstractmethod
    async def authenticate(self) -> None:
        """Authenticate against the remote API and store credentials/tokens."""
        ...

    @abstractmethod
    async def health(self) -> dict:
        """Return connector health.

        Expected keys:
            status   – "healthy" | "degraded" | "unhealthy"
            latency_ms – round-trip latency in milliseconds
            last_sync  – ISO-8601 timestamp of the last successful sync
        """
        ...

    @abstractmethod
    async def fetch_events(self, since: datetime) -> list[dict]:
        """Fetch raw events created after *since* from the source."""
        ...

    @abstractmethod
    async def normalize(self, event: dict) -> SecurityEvent:
        """Convert a single raw event dict into a SecurityEvent."""
        ...

    @abstractmethod
    async def acknowledge(self, event_ids: list[str]) -> None:
        """Mark the given event IDs as processed / acknowledged upstream."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the connection and release resources."""
        ...
