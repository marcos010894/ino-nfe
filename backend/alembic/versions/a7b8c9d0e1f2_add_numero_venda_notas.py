"""Add numero_venda to notas (Nº da venda de origem no InnoSystem)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('numero_venda', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_notas_numero_venda', ['numero_venda'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.drop_index('ix_notas_numero_venda')
        batch_op.drop_column('numero_venda')
