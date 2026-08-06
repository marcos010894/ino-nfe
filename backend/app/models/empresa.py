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
    codigo_municipio: Optional[str] = None  # Código IBGE (7 dígitos) — exigido pela ACBr API
    uf: Optional[str] = None
    
    # Contato
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    
    # Fiscal
    regime_tributario: str = Field(default="Simples Nacional")
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None  # Guardado criptografado

    # Série ativa por modelo. Cliente pode trocar (ex: abandonar série 1 com buracos
    # e recomeçar em série 2 do zero). Numeração `nNF` é MAX+1 dentro de (empresa,
    # modelo, série) — ao trocar de série, o contador reinicia naturalmente.
    serie_nfe: int = Field(default=1)   # modelo 55
    serie_nfce: int = Field(default=1)  # modelo 65
    
    # Certificado Digital A1
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    certificado_vencimento: Optional[datetime] = None
    certificado_emissor: Optional[str] = None
    certificado_sujeito: Optional[str] = None
    
    # Integração ACBr API
    acbr_sincronizado: bool = Field(default=False)
    acbr_ultimo_status: Optional[str] = None
    
    criado_em: datetime = Field(default_factory=datetime.utcnow)

