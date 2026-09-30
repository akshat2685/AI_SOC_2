"""Twin scenarios: the closed intel -> twin -> learn loop, persisted.

Each row is one attack scenario the digital twin ran against the real
detection engine: where the scenario came from (fresh threat intel, a
replay of a real past alert, or a simulated technique), what happened,
whether the engine caught it, and — for evasions — the SOC's own
analysis of what went wrong and how to defend next time.

Global table (the twin tests the shared engine, not tenant data).
Survives restarts, unlike the old in-process evasion list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models import Base


class TwinScenario(Base):
    __tablename__ = "twin_scenarios"
    __table_args__ = (
        Index("ix_twin_scenarios_source_created", "source", "created_at"),
        # Note: ix_twin_scenarios_detected is auto-created by index=True on the column.
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # "intel-ioc" | "alert-replay" | "simulated-technique"
    source: Mapped[str] = mapped_column(String(30), index=True)
    technique_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    tactic: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # What the twin tried: description, IoC values, event summary.
    scenario: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Outcome: did the real engine catch it?
    detected: Mapped[bool] = mapped_column(default=False, index=True)
    detector: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rule_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # The SOC's self-analysis for evasions:
    # {what_happened, why_evaded, how_to_defend[]}. Empty when detected.
    analysis: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Link to the training row this evasion became (if any).
    training_feedback_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)
