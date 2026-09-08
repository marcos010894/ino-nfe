"""Add admin flags: usuarios.is_admin, empresas.bloqueada, empresas.deletada_em

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bloqueada', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('deletada_em', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_empresas_deletada_em', ['deletada_em'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_index('ix_empresas_deletada_em')
        batch_op.drop_column('deletada_em')
        batch_op.drop_column('bloqueada')

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('is_admin')
