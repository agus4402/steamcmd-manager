"""workshop metadata: rich mod fields, dependencies, auto-update

Expands the Workshop feature into a full mod manager: cached metadata on
workshop_mods (title/author/preview/description/counts/sizes/timestamps),
dependency tracking (is_dependency, required_by), a provider column, and a
per-server workshop_auto_update setting. Also widens the status column to fit
the new lifecycle values (queued/downloading/update_available/missing_dependency).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-21 02:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'servers',
        sa.Column(
            'workshop_auto_update',
            sa.String(length=16),
            nullable=False,
            server_default='disabled',
        ),
    )

    op.add_column('workshop_mods', sa.Column('provider', sa.String(length=16), nullable=False, server_default='steam'))
    op.add_column('workshop_mods', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('workshop_mods', sa.Column('author_id', sa.String(length=32), nullable=True))
    op.add_column('workshop_mods', sa.Column('author_name', sa.String(length=255), nullable=True))
    op.add_column('workshop_mods', sa.Column('preview_url', sa.Text(), nullable=True))
    op.add_column('workshop_mods', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('workshop_mods', sa.Column('subscribers', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('workshop_mods', sa.Column('favorites', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('workshop_mods', sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('workshop_mods', sa.Column('time_updated_remote', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workshop_mods', sa.Column('installed_time_updated', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workshop_mods', sa.Column('is_dependency', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('workshop_mods', sa.Column('required_by', sa.String(length=20), nullable=True))

    # Widen status to fit the new lifecycle values.
    op.alter_column('workshop_mods', 'status', type_=sa.String(length=20), existing_type=sa.String(length=16))


def downgrade() -> None:
    op.alter_column('workshop_mods', 'status', type_=sa.String(length=16), existing_type=sa.String(length=20))
    op.drop_column('workshop_mods', 'required_by')
    op.drop_column('workshop_mods', 'is_dependency')
    op.drop_column('workshop_mods', 'installed_time_updated')
    op.drop_column('workshop_mods', 'time_updated_remote')
    op.drop_column('workshop_mods', 'file_size')
    op.drop_column('workshop_mods', 'favorites')
    op.drop_column('workshop_mods', 'subscribers')
    op.drop_column('workshop_mods', 'description')
    op.drop_column('workshop_mods', 'preview_url')
    op.drop_column('workshop_mods', 'author_name')
    op.drop_column('workshop_mods', 'author_id')
    op.drop_column('workshop_mods', 'title')
    op.drop_column('workshop_mods', 'provider')
    op.drop_column('servers', 'workshop_auto_update')
