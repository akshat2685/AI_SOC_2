"""Normalized security event ingestion: security_events table.

Revision ID: 0007_security_events
Revises: 0006_integrations_agents

Adds the Phase 1 telemetry layer:
- security_events: one row per observed endpoint event in a single
  OS-agnostic schema (process / network / file / auth / dns). The typed
  section lives in `payload`; the sensor's untouched record in `raw`.
  Nothing is enriched — what the sensor sent is what is stored.
- endpoint_agents.last_seen_at: bumped on every successful ingest batch
  (distinct from last_heartbeat_at, which is the agent liveness signal).

Enum columns are plain VARCHAR(50) (native_enum=False), matching every
other enum column in this codebase — no native Postgres enum types.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_security_events"
down_revision: Union[str, None] = "0006_integrations_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity_hint", sa.String(length=50), nullable=False, server_default="info"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_security_events_tenant_id", "security_events", ["tenant_id"], unique=False)
    op.create_index("ix_security_events_device_id", "security_events", ["device_id"], unique=False)
    op.create_index("ix_security_events_observed_at", "security_events", ["observed_at"], unique=False)
    op.create_index(
        "ix_security_events_tenant_observed", "security_events", ["tenant_id", "observed_at"], unique=False
    )

    op.add_column(
        "endpoint_agents",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("endpoint_agents", "last_seen_at")
    op.drop_index("ix_security_events_tenant_observed", table_name="security_events")
    op.drop_index("ix_security_events_observed_at", table_name="security_events")
    op.drop_index("ix_security_events_device_id", table_name="security_events")
    op.drop_index("ix_security_events_tenant_id", table_name="security_events")
    op.drop_table("security_events")
