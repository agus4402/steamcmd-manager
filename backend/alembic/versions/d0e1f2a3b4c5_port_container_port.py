"""port container_port: game-side port when it differs from the host port

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-14 01:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: str | None = 'c9d0e1f2a3b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('port_allocations', sa.Column('container_port', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('port_allocations', 'container_port')
