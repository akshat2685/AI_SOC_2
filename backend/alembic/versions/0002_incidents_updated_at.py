"""Add missing updated_at column to incidents (model drift fix).

Revision ID: 0002_incidents_updated_at
Revises: 0001_initial_schema

The 0001 migration was generated before Incident.updated_at was added to the
SQLAlchemy model, so SELECTs against incidents failed on Postgres with
"column incidents.updated_at does not exist".
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_incidents_updated_at"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("incidents", "updated_at")
