"""Add codigo_municipio to Empresa (IBGE municipality code required by ACBr API)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('codigo_municipio', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('codigo_municipio')
