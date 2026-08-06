from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
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
    rascunho_id: Optional[int] = None

class NotaResponse(NotaBase):
    id: int
    empresa_id: Optional[int] = None
    criado_em: datetime
    atualizado_em: datetime

class NotaCancelar(BaseModel):
    justificativa: str

    class Config:
        orm_mode = True


class ReceberVendaCliente(BaseModel):
    # Aceita campos extras (endereco, email, etc.) preservados no json_venda.
    model_config = ConfigDict(extra="allow")

    nome: str
    cpf: Optional[str] = None
    cnpj: Optional[str] = None


class ReceberVendaItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    codigo: Optional[str] = None
    nome: str
    quantidade: float = Field(gt=0)
    valor_unitario: float = Field(ge=0)
    unidade: str = "UN"


class ReceberVendaPagamento(BaseModel):
    model_config = ConfigDict(extra="allow")

    meio_pagamento: str
    valor: float = Field(ge=0)


class ReceberVendaPayload(BaseModel):
    """Formato canônico enviado pelo InnoSystem para /integracao/receber-venda.

    Campos do PDV: cliente + itens (código/nome/qtd/unitário) + desconto + pagamentos.
    O valor_total da nota é calculado no servidor a partir dos itens - desconto.
    Campos extras são preservados (extra="allow") pra não perder dados do integrador.
    """
    model_config = ConfigDict(extra="allow")

    cliente: ReceberVendaCliente
    itens: List[ReceberVendaItem] = Field(min_length=1)
    desconto: float = Field(default=0.0, ge=0)
    pagamentos: List[ReceberVendaPagamento] = []
    numero_pedido_externo: Optional[str] = None


class InutilizacaoRequest(BaseModel):
    """Inutilização de faixa de numeração NF-e/NFC-e (Etapa G do MVP).

    Uso: números que foram "queimados" (gerados no sistema mas nunca autorizados
    pela SEFAZ) precisam ser declarados como inutilizados pra fechar o livro fiscal.
    Não confundir com cancelamento (nota já autorizada e depois anulada).
    """
    modelo: str  # "55" (NF-e) ou "65" (NFC-e)
    serie: int = 1
    numero_inicial: int
    numero_final: int
    justificativa: str
    ano: Optional[int] = None  # default: ano corrente
