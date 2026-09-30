"""Alembic migration 0013: persistent tenant firewall blocklist.

Backs POST /firewall/block + GET /firewall/blocks with real state. Before
this, block/unblock validated the IP, logged, and returned success while
persisting nothing — the UI claimed IPs were blocked when they were not.
"""

revision = "0013_firewall_blocks"
down_revision = "0012_tenant_response_mode"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    import sqlalchemy as sa

    op.execute("SELECT set_config('rls.app_role', 'service', false)")

    op.create_table(
        "firewall_blocks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_firewall_blocks_tenant_id", "firewall_blocks", ["tenant_id"])
    op.create_index("ix_firewall_blocks_ip", "firewall_blocks", ["ip"])


def downgrade():
    from alembic import op

    op.execute("SELECT set_config('rls.app_role', 'service', false)")
    op.drop_index("ix_firewall_blocks_ip", table_name="firewall_blocks")
    op.drop_index("ix_firewall_blocks_tenant_id", table_name="firewall_blocks")
    op.drop_table("firewall_blocks")
