"""Phase 2 detection: alert enrichment columns + detection watermarks.

Revision ID: 0008_detection_alerts
Revises: 0007_security_events

- alerts: add severity, confidence (0-100), device_id, rule_id, evidence (JSON).
  Existing rows keep NULLs; the API falls back to honest defaults for them.
- detection_watermarks: one row per tenant tracking the last detection scan
  (last_scan_at, events_scanned, alerts_created). The scan loop resumes from
  the watermark so events are never double-scanned after a restart.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_detection_alerts"
down_revision: Union[str, None] = "0007_security_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("severity", sa.String(length=20), nullable=True))
    op.add_column("alerts", sa.Column("confidence", sa.Integer(), nullable=True))
    op.add_column("alerts", sa.Column("device_id", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("rule_id", sa.String(length=100), nullable=True))
    op.add_column("alerts", sa.Column("evidence", sa.JSON(), nullable=True))
    op.create_index("ix_alerts_tenant_device", "alerts", ["tenant_id", "device_id"])

    op.create_table(
        "detection_watermarks",
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("detection_watermarks")
    op.drop_index("ix_alerts_tenant_device", table_name="alerts")
    op.drop_column("alerts", "evidence")
    op.drop_column("alerts", "rule_id")
    op.drop_column("alerts", "device_id")
    op.drop_column("alerts", "confidence")
    op.drop_column("alerts", "severity")
