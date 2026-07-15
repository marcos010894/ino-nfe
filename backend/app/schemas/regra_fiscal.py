from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class RegraFiscalBase(BaseModel):
    nome: str
    cfop: str = Field(min_length=4, max_length=4)
    ncm_padrao: str = Field(min_length=8, max_length=8)
    origem_icms: str = "0"
    cst_csosn: str
    icms_aliquota: float = 0.0
    pis_cst: str = "01"
    pis_aliquota: float = 0.0
    cofins_cst: str = "01"
    cofins_aliquota: float = 0.0
    padrao: bool = False

class RegraFiscalCreate(RegraFiscalBase):
    pass

class RegraFiscalUpdate(RegraFiscalBase):
    pass

class RegraFiscalResponse(RegraFiscalBase):
    id: int
    empresa_id: int
    criado_em: datetime
