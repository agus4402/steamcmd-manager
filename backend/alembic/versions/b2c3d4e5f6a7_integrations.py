"""integrations: providers, encrypted credentials, tunnels

Adds the extensible integrations framework tables:
- integrations: one link per provider (Playit, ...)
- integration_credentials: 1:1 Fernet-encrypted secret store
- integration_tunnels: tunnels owned by tunnel-capable providers

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'integrations',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('account_label', sa.String(length=255), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'user_id', name='uq_integration_provider_user'),
    )
    op.create_index(op.f('ix_integrations_provider'), 'integrations', ['provider'], unique=False)

    op.create_table(
        'integration_credentials',
        sa.Column('integration_id', sa.String(length=12), nullable=False),
        sa.Column('encrypted_credentials', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('integration_id'),
    )

    op.create_table(
        'integration_tunnels',
        sa.Column('id', sa.String(length=12), nullable=False),
        sa.Column('integration_id', sa.String(length=12), nullable=False),
        sa.Column('server_id', sa.String(length=12), nullable=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('remote_domain', sa.String(length=255), nullable=True),
        sa.Column('local_port', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.String(length=8), nullable=False),
        sa.Column('external_id', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_integration_tunnels_integration_id'),
        'integration_tunnels',
        ['integration_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_integration_tunnels_integration_id'), table_name='integration_tunnels')
    op.drop_table('integration_tunnels')
    op.drop_table('integration_credentials')
    op.drop_index(op.f('ix_integrations_provider'), table_name='integrations')
    op.drop_table('integrations')
