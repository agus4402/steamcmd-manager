"""add is_primary to port_allocations

Supports consecutive-port allocation (e.g. Valheim's game + query UDP ports):
the base port of a block is primary and exposed as {{PORT_<name>}}; extra ports
are published to Docker but never referenced directly.

Revision ID: a1b2c3d4e5f6
Revises: f3ede215f001
Create Date: 2026-06-18 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f3ede215f001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable first to backfill existing rows, then enforce NOT NULL.
    op.add_column(
        'port_allocations',
        sa.Column('is_primary', sa.Boolean(), nullable=True),
    )
    op.execute('UPDATE port_allocations SET is_primary = true WHERE is_primary IS NULL')
    op.alter_column(
        'port_allocations',
        'is_primary',
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text('true'),
    )


def downgrade() -> None:
    op.drop_column('port_allocations', 'is_primary')
