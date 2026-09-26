"""Alembic migration 0010: twin_scenarios for the closed intel->twin->learn loop."""

revision = "0010_twin_scenarios"
down_revision = "0009_autonomous_loop"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    op.create_table(
        "twin_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(30), nullable=False, index=True),
        sa.Column("technique_id", sa.String(20), nullable=True, index=True),
        sa.Column("tactic", sa.String(50), nullable=True),
        sa.Column("scenario", JSONB(), nullable=False, server_default="{}"),
        sa.Column("detected", sa.Boolean(), nullable=False, server_default="false", index=True),
        sa.Column("detector", sa.String(50), nullable=True),
        sa.Column("rule_id", sa.String(50), nullable=True),
        sa.Column("analysis", JSONB(), nullable=False, server_default="{}"),
        sa.Column("training_feedback_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_twin_scenarios_source_created", "twin_scenarios", ["source", "created_at"])
    op.create_index("ix_twin_scenarios_detected", "twin_scenarios", ["detected"])


def downgrade():
    from alembic import op
    op.drop_index("ix_twin_scenarios_detected", table_name="twin_scenarios")
    op.drop_index("ix_twin_scenarios_source_created", table_name="twin_scenarios")
    op.drop_table("twin_scenarios")
