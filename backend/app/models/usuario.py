from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    email: str = Field(index=True, unique=True)
    senha_hash: str
    cpf: str = Field(default="")
    telefone: str = Field(default="")
    ativo: bool = Field(default=True)
    token_integracao: Optional[str] = Field(default=None, unique=True, index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
