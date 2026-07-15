from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Empresa(SQLModel, table=True):
    __tablename__ = "empresas"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    razao_social: str
    nome_fantasia: str
    cnpj: str = Field(unique=True, index=True)
    inscricao_estadual: Optional[str] = None
    
    # Endereço
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    
    # Contato
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    
    # Fiscal
    regime_tributario: str = Field(default="Simples Nacional")
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None  # Guardado criptografado
    
    criado_em: datetime = Field(default_factory=datetime.utcnow)
