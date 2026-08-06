"""Expand RegraFiscal with Reforma Tributária, IPI/II, ICMS-ST, FCP, DIFAL, cBenef, CEST

Revision ID: a1b2c3d4e5f6
Revises: fdedffc7d917
Create Date: 2026-08-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fdedffc7d917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_STRING_COLUMNS = [
    'cest',
    'cbenef',
    'mod_bc',
    'mot_des_icms',
    'mod_bc_st',
    'ipi_cst',
    'ipi_cenq',
    'cbs_cst',
    'cbs_cclass_trib',
    'is_cst',
]

NEW_FLOAT_COLUMNS = [
    'p_red_bc',
    'v_icms_deson',
    'p_mva_st',
    'p_red_bc_st',
    'p_icms_st',
    'p_fcp',
    'p_fcp_st',
    'p_icms_uf_dest',
    'p_icms_interpart',
    'p_fcp_uf_dest',
    'ipi_aliquota',
    'ii_aliquota',
    'cbs_aliquota',
    'ibs_uf_aliquota',
    'ibs_mun_aliquota',
    'is_aliquota',
]

NEW_BOOL_COLUMNS = [
    'regime_monofasico',
    'credito_presumido',
    'diferimento',
]


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('regras_fiscais', schema=None) as batch_op:
        for col in NEW_STRING_COLUMNS:
            batch_op.add_column(sa.Column(col, sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        for col in NEW_FLOAT_COLUMNS:
            batch_op.add_column(sa.Column(col, sa.Float(), nullable=True))
        for col in NEW_BOOL_COLUMNS:
            batch_op.add_column(sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('regras_fiscais', schema=None) as batch_op:
        for col in NEW_BOOL_COLUMNS:
            batch_op.drop_column(col)
        for col in NEW_FLOAT_COLUMNS:
            batch_op.drop_column(col)
        for col in NEW_STRING_COLUMNS:
            batch_op.drop_column(col)
