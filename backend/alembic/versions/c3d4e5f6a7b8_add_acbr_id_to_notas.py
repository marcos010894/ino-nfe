"""Add acbr_id to notas

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-01 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acbr_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True))
        batch_op.create_index(op.f('ix_notas_acbr_id'), ['acbr_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_notas_acbr_id'))
        batch_op.drop_column('acbr_id')
