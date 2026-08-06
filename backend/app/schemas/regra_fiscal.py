from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class RegraFiscalBase(BaseModel):
    nome: str
    cfop: str = Field(min_length=4, max_length=4)
    ncm_padrao: str = Field(min_length=8, max_length=8)
    cest: Optional[str] = None
    cbenef: Optional[str] = None

    # ICMS / Simples
    origem_icms: str = "0"
    cst_csosn: str
    icms_aliquota: float = 0.0
    mod_bc: Optional[str] = None
    p_red_bc: Optional[float] = None
    mot_des_icms: Optional[str] = None
    v_icms_deson: Optional[float] = None

    # ICMS-ST
    mod_bc_st: Optional[str] = None
    p_mva_st: Optional[float] = None
    p_red_bc_st: Optional[float] = None
    p_icms_st: Optional[float] = None

    # FCP
    p_fcp: Optional[float] = None
    p_fcp_st: Optional[float] = None

    # DIFAL
    p_icms_uf_dest: Optional[float] = None
    p_icms_interpart: Optional[float] = None
    p_fcp_uf_dest: Optional[float] = None

    # IPI
    ipi_cst: Optional[str] = None
    ipi_aliquota: Optional[float] = None
    ipi_cenq: Optional[str] = None

    # II
    ii_aliquota: Optional[float] = None

    # PIS / COFINS
    pis_cst: str = "01"
    pis_aliquota: float = 0.0
    cofins_cst: str = "01"
    cofins_aliquota: float = 0.0

    # Reforma Tributária — CBS
    cbs_cst: Optional[str] = None
    cbs_cclass_trib: Optional[str] = None
    cbs_aliquota: Optional[float] = None

    # Reforma Tributária — IBS
    ibs_uf_aliquota: Optional[float] = None
    ibs_mun_aliquota: Optional[float] = None

    # Reforma Tributária — IS
    is_cst: Optional[str] = None
    is_aliquota: Optional[float] = None

    # Flags
    regime_monofasico: bool = False
    credito_presumido: bool = False
    diferimento: bool = False

    padrao: bool = False

class RegraFiscalCreate(RegraFiscalBase):
    pass

class RegraFiscalUpdate(RegraFiscalBase):
    pass

class RegraFiscalResponse(RegraFiscalBase):
    id: int
    empresa_id: int
    criado_em: datetime
