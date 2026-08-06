from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class RegraFiscal(SQLModel, table=True):
    __tablename__ = "regras_fiscais"

    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresas.id", index=True)
    nome: str

    # Parâmetros Base
    cfop: str = Field(min_length=4, max_length=4)
    ncm_padrao: str = Field(min_length=8, max_length=8)
    cest: Optional[str] = Field(default=None, max_length=7)
    cbenef: Optional[str] = Field(default=None, max_length=10)

    # ICMS / Simples
    origem_icms: str = Field(default="0", max_length=1)  # 0 a 8
    cst_csosn: str = Field(max_length=4)
    icms_aliquota: float = Field(default=0.0)
    mod_bc: Optional[str] = Field(default=None, max_length=1)  # 0-3
    p_red_bc: Optional[float] = Field(default=None)
    mot_des_icms: Optional[str] = Field(default=None, max_length=2)
    v_icms_deson: Optional[float] = Field(default=None)

    # ICMS-ST
    mod_bc_st: Optional[str] = Field(default=None, max_length=1)  # 0-5
    p_mva_st: Optional[float] = Field(default=None)
    p_red_bc_st: Optional[float] = Field(default=None)
    p_icms_st: Optional[float] = Field(default=None)

    # FCP
    p_fcp: Optional[float] = Field(default=None)
    p_fcp_st: Optional[float] = Field(default=None)

    # DIFAL (EC 87/2015)
    p_icms_uf_dest: Optional[float] = Field(default=None)
    p_icms_interpart: Optional[float] = Field(default=None)
    p_fcp_uf_dest: Optional[float] = Field(default=None)

    # IPI
    ipi_cst: Optional[str] = Field(default=None, max_length=2)
    ipi_aliquota: Optional[float] = Field(default=None)
    ipi_cenq: Optional[str] = Field(default=None, max_length=3)

    # II (Importação)
    ii_aliquota: Optional[float] = Field(default=None)

    # PIS / COFINS (regime antigo, mantido para itens em transição)
    pis_cst: str = Field(default="01", max_length=2)
    pis_aliquota: float = Field(default=0.0)
    cofins_cst: str = Field(default="01", max_length=2)
    cofins_aliquota: float = Field(default=0.0)

    # Reforma Tributária — CBS (federal)
    cbs_cst: Optional[str] = Field(default=None, max_length=3)
    cbs_cclass_trib: Optional[str] = Field(default=None, max_length=6)
    cbs_aliquota: Optional[float] = Field(default=None)

    # Reforma Tributária — IBS
    ibs_uf_aliquota: Optional[float] = Field(default=None)
    ibs_mun_aliquota: Optional[float] = Field(default=None)

    # Reforma Tributária — IS (Imposto Seletivo)
    is_cst: Optional[str] = Field(default=None, max_length=3)
    is_aliquota: Optional[float] = Field(default=None)

    # Flags de regime da Reforma
    regime_monofasico: bool = Field(default=False)
    credito_presumido: bool = Field(default=False)
    diferimento: bool = Field(default=False)

    padrao: bool = Field(default=False)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
