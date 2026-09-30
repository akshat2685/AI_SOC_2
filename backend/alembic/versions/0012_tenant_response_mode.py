"""Alembic migration 0012: per-tenant response mode + sensor poll interval.

- tenants.response_mode: 'dry_run' | 'approvals_only' | 'auto_contain'.
  New tenants default to 'dry_run' (observe first, contain never). Existing
  tenants keep their current behavior ('auto_contain') so the migration
  never silently changes a live tenant's safety posture.
- tenants.poll_interval_s: sensor command-poll cadence for this tenant
  (default 30). The sensor reads it from the poll response; "real-time"
  becomes a dial, not a slogan.

The UPDATE runs under rls.app_role='service' because migration 0011's
FORCE ROW LEVEL SECURITY is already active at this point.
"""

revision = "0012_tenant_response_mode"
down_revision = "0011_rls_enforcement"
branch_labels = None
depends_on = None

RESPONSE_MODES = ("dry_run", "approvals_only", "auto_contain")


def upgrade():
    from alembic import op
    import sqlalchemy as sa

    op.execute("SELECT set_config('rls.app_role', 'service', false)")

    op.add_column(
        "tenants",
        sa.Column(
            "response_mode",
            sa.String(16),
            nullable=False,
            server_default="dry_run",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "poll_interval_s",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )

    # Preserve current behavior for tenants that already exist: until this
    # migration, auto-contain was the global policy.
    op.execute("UPDATE tenants SET response_mode = 'auto_contain'")

    op.execute("RESET rls.app_role")


def downgrade():
    from alembic import op

    op.drop_column("tenants", "poll_interval_s")
    op.drop_column("tenants", "response_mode")
