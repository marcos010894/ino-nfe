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
    
    # ICMS / Simples
    origem_icms: str = Field(default="0", max_length=1)  # 0 a 8
    cst_csosn: str = Field(max_length=4)
    icms_aliquota: float = Field(default=0.0)
    
    # PIS/COFINS
    pis_cst: str = Field(default="01", max_length=2)
    pis_aliquota: float = Field(default=0.0)
    cofins_cst: str = Field(default="01", max_length=2)
    cofins_aliquota: float = Field(default=0.0)
    
    padrao: bool = Field(default=False)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
