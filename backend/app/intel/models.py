"""Threat-intel IoC storage.

GLOBAL table (no tenant_id): the same malicious infrastructure threatens
every tenant, and the detection engine's C2 lookups are tenant-independent.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.domain.models import Base


class ThreatIntelIoC(Base):
    """One indicator of compromise from a threat-intel feed."""

    __tablename__ = "threat_intel_iocs"
    __table_args__ = (
        UniqueConstraint(
            "source", "ioc_type", "value", name="uq_intel_source_type_value"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Feed name: "cisa-kev" | "threatfox" | "urlhaus"
    source: Mapped[str] = mapped_column(String(50), index=True)
    # "ip" | "domain" | "url" | "hash" | "cve"
    ioc_type: Mapped[str] = mapped_column(String(20), index=True)
    value: Mapped[str] = mapped_column(String(1024))
    threat_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    malware_family: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    first_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
