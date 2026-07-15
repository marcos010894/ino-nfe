from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EmpresaBase(BaseModel):
    razao_social: str
    nome_fantasia: str
    cnpj: str
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    regime_tributario: str = "Simples Nacional"
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None

class EmpresaCreate(EmpresaBase):
    pass

class EmpresaUpdate(EmpresaBase):
    pass

class CertificadoResponse(BaseModel):
    id: int
    validade: Optional[datetime] = None
    criado_em: datetime

class EmpresaResponse(EmpresaBase):
    id: int
    usuario_id: int
    criado_em: datetime
    # Removemos o token real e enviamos apenas boolean se existe para o frontend saber
    has_csc_token: bool = False
    certificado: Optional[CertificadoResponse] = None
