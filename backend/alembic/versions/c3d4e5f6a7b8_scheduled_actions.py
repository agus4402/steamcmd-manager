"""scheduled_actions: cron-driven server automation

Adds the scheduled_actions table backing the scheduler: one row per recurring
task (start/stop/restart/update/backup) for a server, as a 5-field crontab.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-20 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'scheduled_actions',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('server_id', sa.String(length=12), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('cron', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=16), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_scheduled_actions_server_id'), 'scheduled_actions', ['server_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_scheduled_actions_server_id'), table_name='scheduled_actions')
    op.drop_table('scheduled_actions')
