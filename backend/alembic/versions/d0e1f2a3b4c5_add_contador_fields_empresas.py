"""Add contador fields to empresas + envio_contador_log table

Central de Documentos v3 — envio de XMLs pro contador (manual + cron dia 1-28).
Modal "Dados do contador" (V3.6) grava aqui. Log de envio é pra idempotência do
cron (não enviar 2x no mesmo mês).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-28 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nome_contador', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('email_contador', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('email_cc_contador', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        # 1..28 — evita mês fevereiro sem dia 29/30/31. NULL = envio automático desligado.
        batch_op.add_column(sa.Column('dia_envio_contador', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('envio_automatico_contador', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        # Templates com placeholders {contador}, {empresa}, {periodo}
        batch_op.add_column(sa.Column('assunto_email_contador', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('mensagem_email_contador', sa.Text(), nullable=True))

    # Log de envio pro contador. periodo_ref no formato "YYYY-MM" — unique
    # por (empresa, período) pra o cron não disparar 2x pro mesmo mês.
    op.create_table(
        'envio_contador_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('periodo_ref', sa.String(length=7), nullable=False),  # "2026-09"
        sa.Column('enviado_em', sa.DateTime(), nullable=False),
        sa.Column('destinatarios', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('qtd_notas', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('ok', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('erro', sa.Text(), nullable=True),
        sa.Column('disparado_por', sqlmodel.sql.sqltypes.AutoString(), nullable=True),  # "manual" | "cron"
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('envio_contador_log', schema=None) as batch_op:
        batch_op.create_index('ix_envio_contador_log_empresa_id', ['empresa_id'])
        batch_op.create_index('ix_envio_contador_log_periodo_ref', ['periodo_ref'])
        # Idempotência: só um envio OK por (empresa, período). Se falhou, permite
        # retry — o cron filtra por `ok=True` mesmo assim.
        batch_op.create_index('ix_envio_contador_log_empresa_periodo', ['empresa_id', 'periodo_ref'])


def downgrade() -> None:
    with op.batch_alter_table('envio_contador_log', schema=None) as batch_op:
        batch_op.drop_index('ix_envio_contador_log_empresa_periodo')
        batch_op.drop_index('ix_envio_contador_log_periodo_ref')
        batch_op.drop_index('ix_envio_contador_log_empresa_id')
    op.drop_table('envio_contador_log')

    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('mensagem_email_contador')
        batch_op.drop_column('assunto_email_contador')
        batch_op.drop_column('envio_automatico_contador')
        batch_op.drop_column('dia_envio_contador')
        batch_op.drop_column('email_cc_contador')
        batch_op.drop_column('email_contador')
        batch_op.drop_column('nome_contador')
