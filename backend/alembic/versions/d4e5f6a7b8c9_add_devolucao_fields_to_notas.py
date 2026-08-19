"""Add devolucao fields to notas

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('finalidade', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('nota_referenciada_chave', sqlmodel.sql.sqltypes.AutoString(length=44), nullable=True))
        batch_op.add_column(sa.Column('nota_referenciada_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('natureza_operacao', sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.drop_column('natureza_operacao')
        batch_op.drop_column('nota_referenciada_id')
        batch_op.drop_column('nota_referenciada_chave')
        batch_op.drop_column('finalidade')
