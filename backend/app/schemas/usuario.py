from pydantic import BaseModel, EmailStr
from typing import Optional
class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    cpf: str
    telefone: str

class UsuarioLogin(BaseModel):
    email: EmailStr
    senha: str

class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: EmailStr
    cpf: str
    telefone: str
    ativo: bool
    token_integracao: Optional[str] = None
class Token(BaseModel):
    access_token: str
    token_type: str
