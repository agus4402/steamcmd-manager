"""workshop submods: per-mod-id toggles + load order inside workshop items

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-14 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: str | None = 'b8c9d0e1f2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Branch the item was last inspected for (NULL = never inspected).
    op.add_column('workshop_mods', sa.Column('inspected_branch', sa.String(length=64), nullable=True))
    op.create_table(
        'workshop_submods',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('server_id', sa.String(length=12), nullable=False),
        sa.Column('workshop_mod_id', sa.String(length=12), nullable=False),
        sa.Column('mod_id', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('folder', sa.String(length=512), nullable=False),
        sa.Column('requires', sa.JSON(), nullable=False),
        sa.Column('maps', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('load_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workshop_mod_id'], ['workshop_mods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('server_id', 'mod_id', name='uq_workshop_submod_server_mod'),
    )
    op.create_index(op.f('ix_workshop_submods_server_id'), 'workshop_submods', ['server_id'], unique=False)
    op.create_index(
        op.f('ix_workshop_submods_workshop_mod_id'), 'workshop_submods', ['workshop_mod_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_workshop_submods_workshop_mod_id'), table_name='workshop_submods')
    op.drop_index(op.f('ix_workshop_submods_server_id'), table_name='workshop_submods')
    op.drop_table('workshop_submods')
    op.drop_column('workshop_mods', 'inspected_branch')
