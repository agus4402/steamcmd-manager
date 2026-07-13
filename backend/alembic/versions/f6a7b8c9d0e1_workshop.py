"""workshop: server workshop_app_id + workshop_mods

Adds Steam Workshop support: a workshop_app_id column on servers (copied from the
template when the game is workshop-capable; NULL otherwise) and a workshop_mods
table tracking installed items per server.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-21 01:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('servers', sa.Column('workshop_app_id', sa.Integer(), nullable=True))

    op.create_table(
        'workshop_mods',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('server_id', sa.String(length=12), nullable=False),
        sa.Column('item_id', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('server_id', 'item_id', name='uq_workshop_server_item'),
    )
    op.create_index(op.f('ix_workshop_mods_server_id'), 'workshop_mods', ['server_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workshop_mods_server_id'), table_name='workshop_mods')
    op.drop_table('workshop_mods')
    op.drop_column('servers', 'workshop_app_id')
