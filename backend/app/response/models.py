"""Device command queue for the autonomous response loop.

A DeviceCommand is an instruction the backend wants one specific endpoint
sensor to execute: kill a process, block an IP, quarantine a file, or remove
a persistence mechanism. The sensor polls GET /agents/{device_id}/commands
and acks each one after executing.

Table: device_commands (migration is owned by the parent agent — this file
only declares the model).

Lifecycle: pending -> delivered (sensor fetched it) -> acked | failed.
A command stuck in "delivered" is re-offered on the next poll so a crashed
sensor never loses it silently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.domain.models import Base

# Closed allowlist. Both the backend policy engine AND the sensor enforce it;
# anything not on this list is refused at both ends.
COMMAND_ACTIONS = ("kill_process", "block_ip", "quarantine_file", "remove_persistence")

# Destructive actions (data loss / persistence removal) are never auto-issued
# except under the strict gate in response/policy.py.
DESTRUCTIVE_ACTIONS = ("quarantine_file", "remove_persistence")

COMMAND_STATUSES = ("pending", "delivered", "acked", "failed")


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_device_commands_tenant_device_status", "tenant_id", "device_id", "status"),
    )
