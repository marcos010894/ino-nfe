from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Certificado(SQLModel, table=True):
    __tablename__ = "certificados"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresas.id", index=True)
    arquivo_path: str
    senha_criptografada: str
    validade: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
