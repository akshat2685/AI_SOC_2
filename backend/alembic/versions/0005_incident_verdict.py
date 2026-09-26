"""Add analyst verdict + notes to incidents.

Revision ID: 0005_incident_verdict
Revises: 0004_remaining_tables

POST /incidents/{id}/verdict and PUT /incidents/{id} now persist the
analyst's verdict and notes instead of returning hardcoded values.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_incident_verdict"
down_revision: Union[str, None] = "0004_remaining_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("verdict", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "incidents",
        sa.Column("analyst_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "analyst_notes")
    op.drop_column("incidents", "verdict")
