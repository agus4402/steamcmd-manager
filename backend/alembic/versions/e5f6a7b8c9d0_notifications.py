"""notifications: in-app alerts

Adds the notifications table backing the notification center: one row per event
(crash, failed/completed install or backup, failed scheduled action), optionally
linked to a server (link nulled, not cascaded, on server delete).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-21 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('server_id', sa.String(length=12), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_server_id'), 'notifications', ['server_id'], unique=False)
    op.create_index(op.f('ix_notifications_read'), 'notifications', ['read'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_server_id'), table_name='notifications')
    op.drop_table('notifications')
