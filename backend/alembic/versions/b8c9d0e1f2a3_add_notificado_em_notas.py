"""Add notificado_em to notas (cursor de piggyback pra GET /integracao/notas?com_mudancas)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notificado_em', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_notas_notificado_em', ['notificado_em'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('notas', schema=None) as batch_op:
        batch_op.drop_index('ix_notas_notificado_em')
        batch_op.drop_column('notificado_em')
