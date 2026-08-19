from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Nota(SQLModel, table=True):
    __tablename__ = "notas"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True, default=1)
    empresa_id: Optional[int] = Field(default=None, foreign_key="empresas.id", index=True)
    modelo: str = Field(default="65", max_length=2)  # "65" = NFC-e, "55" = NF-e
    status: str = Field(default="rascunho", max_length=20)  # rascunho, processando, autorizada, rejeitada, cancelada
    chave_acesso: Optional[str] = Field(default=None, max_length=44)
    acbr_id: Optional[str] = Field(default=None, max_length=64, index=True)  # id interno ACBr (nfc_xxx / nfe_xxx) — usado em GET XML/PDF e cancelamento
    numero: Optional[int] = None
    serie: Optional[int] = None
    valor_total: float = Field(default=0.0)
    
    json_venda: str = Field(default="{}")  # JSON colado do InnoSystem
    payload_enviado: Optional[str] = Field(default=None)  # JSON enviado para a ACBr API
    resposta_integradora: Optional[str] = Field(default=None)  # Retorno completo da ACBr API
    
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None

    # Devolução (finNFe=4). NULL = emissão normal (retro-compat).
    finalidade: Optional[int] = Field(default=None)  # 1=normal, 2=complementar, 3=ajuste, 4=devolução
    nota_referenciada_chave: Optional[str] = Field(default=None, max_length=44)
    nota_referenciada_id: Optional[int] = Field(default=None)
    natureza_operacao: Optional[str] = Field(default=None, max_length=120)

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
