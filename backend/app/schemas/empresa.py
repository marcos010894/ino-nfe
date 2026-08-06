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
    codigo_municipio: Optional[str] = None
    uf: Optional[str] = None
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    regime_tributario: str = "Simples Nacional"
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None
    # Série ativa por modelo (cliente pode trocar via UI para reiniciar numeração)
    serie_nfe: int = 1
    serie_nfce: int = 1

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
    has_csc_token: bool = False
    
    # Certificado Info (Apenas metadados, nunca devolve o base64 e a senha para o front)
    has_certificado: bool = False
    certificado_vencimento: Optional[datetime] = None
    certificado_emissor: Optional[str] = None
    certificado_sujeito: Optional[str] = None
    
    # Integração ACBr
    acbr_sincronizado: bool = False
    acbr_ultimo_status: Optional[str] = None

