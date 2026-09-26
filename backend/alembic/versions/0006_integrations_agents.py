"""Integrations platform tables: integrations, endpoint_agents, onboarding_state.

Revision ID: 0006_integrations_agents
Revises: 0005_incident_verdict

Adds the EDYSOR connectivity layer:
- integrations: connected security products / data sources per tenant
  (config stores only non-secret fields; raw credentials are never persisted).
- endpoint_agents: enrolled Windows/macOS/Linux agents, keyed by a
  server-generated device_id (never by hostname alone).
- onboarding_state: per-tenant wizard progress.

Enum columns are plain VARCHAR(50) (native_enum=False), matching every
other enum column in this codebase — no native Postgres enum types.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_integrations_agents"
down_revision: Union[str, None] = "0005_incident_verdict"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("connector_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="disconnected"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("has_credentials", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"], unique=False)
    op.create_index("ix_integrations_connector_key", "integrations", ["connector_key"], unique=False)

    op.create_table(
        "endpoint_agents",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("os_version", sa.String(length=100), nullable=True),
        sa.Column("arch", sa.String(length=50), nullable=True),
        sa.Column("agent_version", sa.String(length=50), nullable=True),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="unregistered"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_endpoint_agents_tenant_id", "endpoint_agents", ["tenant_id"], unique=False)
    op.create_index("ix_endpoint_agents_device_id", "endpoint_agents", ["device_id"], unique=True)

    op.create_table(
        "onboarding_state",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, unique=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_steps", sa.JSON(), nullable=False),
        sa.Column("skipped_steps", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_onboarding_state_tenant_id", "onboarding_state", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_onboarding_state_tenant_id", table_name="onboarding_state")
    op.drop_table("onboarding_state")
    op.drop_index("ix_endpoint_agents_device_id", table_name="endpoint_agents")
    op.drop_index("ix_endpoint_agents_tenant_id", table_name="endpoint_agents")
    op.drop_table("endpoint_agents")
    op.drop_index("ix_integrations_connector_key", table_name="integrations")
    op.drop_index("ix_integrations_tenant_id", table_name="integrations")
    op.drop_table("integrations")
