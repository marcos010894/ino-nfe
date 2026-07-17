from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class NotaBase(BaseModel):
    modelo: str = "65"
    status: str = "rascunho"
    chave_acesso: Optional[str] = None
    numero: Optional[int] = None
    serie: Optional[int] = None
    valor_total: float = 0.0
    json_venda: str = "{}"
    payload_enviado: Optional[str] = None
    resposta_integradora: Optional[str] = None
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None

class NotaCreate(BaseModel):
    json_venda: str
    modelo: Optional[str] = "65"

class NotaResponse(NotaBase):
    id: int
    empresa_id: int
    criado_em: datetime
    atualizado_em: datetime

class NotaCancelar(BaseModel):
    justificativa: str

    class Config:
        orm_mode = True
