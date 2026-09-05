"""Add proximo_nnf_inicial_nfe/nfce to Empresa (numero inicial migracao ERP)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-05 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proximo_nnf_inicial_nfe', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('proximo_nnf_inicial_nfce', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('proximo_nnf_inicial_nfce')
        batch_op.drop_column('proximo_nnf_inicial_nfe')
