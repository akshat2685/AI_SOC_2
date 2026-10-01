"""Alembic migration 0014: ml_retrain_runs — auto-retrain audit trail.

Backs the automatic gated retrain (app/ml/auto_retrain.py): every time
the evaluator finds enough new training_feedback rows and runs the gated
retrain, the outcome (rows used, gate result, model versions) persists
here so GET /ml/models can report the learning loop's real history.
Global table — the models themselves are global, not tenant-scoped.
"""

revision = "0014_ml_retrain_runs"
down_revision = "0013_firewall_blocks"
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    import sqlalchemy as sa

    op.execute("SELECT set_config('rls.app_role', 'service', false)")

    op.create_table(
        "ml_retrain_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_rows_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_by_source", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model_version_before", sa.String(80), nullable=True),
        sa.Column("model_version_after", sa.String(80), nullable=True),
        sa.Column("triage_accuracy", sa.Float(), nullable=True),
        sa.Column("anomaly_fpr", sa.Float(), nullable=True),
        sa.Column("gate_failures", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
    )
    op.create_index("ix_ml_retrain_runs_trigger", "ml_retrain_runs", ["trigger"])
    op.create_index("ix_ml_retrain_runs_status", "ml_retrain_runs", ["status"])


def downgrade():
    from alembic import op

    op.execute("SELECT set_config('rls.app_role', 'service', false)")
    op.drop_index("ix_ml_retrain_runs_status", table_name="ml_retrain_runs")
    op.drop_index("ix_ml_retrain_runs_trigger", table_name="ml_retrain_runs")
    op.drop_table("ml_retrain_runs")
