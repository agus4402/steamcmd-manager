"""server map_order: user order/toggles for game maps from workshop mods

Also clears workshop_mods.inspected_branch so every item is re-inspected with
the map.info-based map detection.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-14 02:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: str | None = 'd0e1f2a3b4c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('servers', sa.Column('map_order', sa.JSON(), nullable=True))
    op.execute("UPDATE workshop_mods SET inspected_branch = NULL")


def downgrade() -> None:
    op.drop_column('servers', 'map_order')
