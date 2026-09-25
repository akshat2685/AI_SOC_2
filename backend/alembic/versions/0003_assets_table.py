"""Create missing assets table (model drift fix).

Revision ID: 0003_assets_table
Revises: 0002_incidents_updated_at

The Asset SQLAlchemy model existed but the 0001 migration never created the
assets table, so GET /api/v1/digital_twin/topology failed on Postgres with
'relation "assets" does not exist'.

Note: criticality is stored as VARCHAR(50), following the convention used in
0001 for the other enum-mapped columns (role, severity, status). SQLAlchemy's
Enum type converts to/from the Python enum on read/write.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_assets_table"
down_revision: Union[str, None] = "0002_incidents_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=False),
        sa.Column("asset_type", sa.String(length=100), nullable=False),
        sa.Column("criticality", sa.String(length=50), nullable=False),
    )
    op.create_index("ix_assets_id", "assets", ["id"], unique=False)
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assets_tenant_id", table_name="assets")
    op.drop_index("ix_assets_id", table_name="assets")
    op.drop_table("assets")
