"""Autonomous defense loop: threat intel, self-learning feedback, device commands.

Revision ID: 0009_autonomous_loop
Revises: 0008_detection_alerts

- threat_intel_iocs: IoCs from free feeds (CISA KEV, URLhaus, ThreatFox).
  Global table (no tenant_id — intel is the same for every tenant), unique
  on (source, ioc_type, value).
- training_feedback: labeled rows for the self-learning retrain loop
  (analyst verdicts, sparring evasions). tenant-scoped.
- device_commands: pending commands for endpoint agents (kill_process,
  block_ip, quarantine_file, remove_persistence). tenant-scoped, polled by
  the sensor every ~30s.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_autonomous_loop"
down_revision: Union[str, None] = "0008_detection_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "threat_intel_iocs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("source", sa.String(length=50), nullable=False, index=True),
        sa.Column("ioc_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column("threat_type", sa.String(length=100), nullable=True, index=True),
        sa.Column("malware_family", sa.String(length=100), nullable=True, index=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "ioc_type", "value", name="uq_intel_source_type_value"),
    )

    op.create_table(
        "training_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id"), nullable=True, index=True),
        sa.Column("device_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("feature_vector", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.Column("technique_id", sa.String(length=20), nullable=True),
        sa.Column("tactic", sa.String(length=50), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("source", sa.String(length=30), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Index("ix_training_feedback_source_created", "source", "created_at"),
    )

    op.create_table(
        "device_commands",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("device_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Index("ix_device_commands_tenant_device_status", "tenant_id", "device_id", "status"),
    )


def downgrade() -> None:
    op.drop_table("device_commands")
    op.drop_table("training_feedback")
    op.drop_table("threat_intel_iocs")
