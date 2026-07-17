from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Nota(SQLModel, table=True):
    __tablename__ = "notas"

    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresas.id", index=True)
    modelo: str = Field(default="65", max_length=2)  # "65" = NFC-e, "55" = NF-e
    status: str = Field(default="rascunho", max_length=20)  # rascunho, processando, autorizada, rejeitada, cancelada
    chave_acesso: Optional[str] = Field(default=None, max_length=44)
    numero: Optional[int] = None
    serie: Optional[int] = None
    valor_total: float = Field(default=0.0)
    
    json_venda: str = Field(default="{}")  # JSON colado do InnoSystem
    payload_enviado: Optional[str] = Field(default=None)  # JSON enviado para a ACBr API
    resposta_integradora: Optional[str] = Field(default=None)  # Retorno completo da ACBr API
    
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None
    
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
