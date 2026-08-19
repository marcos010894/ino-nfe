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


class DestinatarioInput(BaseModel):
    """Destinatário da devolução (o "cliente" da NF-e de devolução).

    Numa devolução de compra emitida pela loja, o destinatário é o fornecedor
    da nota original. Numa devolução de venda, é o cliente que comprou.
    """
    model_config = ConfigDict(extra="allow")

    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    nome: str
    ie: Optional[str] = None  # "ISENTO" ou dígitos
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cep: Optional[str] = None
    municipio: Optional[str] = None
    codigo_municipio: Optional[str] = None
    uf: Optional[str] = None


class DevolucaoItemInput(BaseModel):
    """Item da devolução, com tributos espelhados do XML original."""
    model_config = ConfigDict(extra="allow")

    codigo: str
    descricao: str
    ncm: str
    cfop: str  # já convertido para CFOP de devolução (1xxx/2xxx/3xxx)
    quantidade: float = Field(gt=0)
    valor_unitario: float = Field(ge=0)
    unidade: str = "UN"
    cst_csosn: str

    # Tributos espelhados do XML original (opcionais, mas recomendado preencher)
    icms_aliquota: Optional[float] = None
    pis_cst: Optional[str] = None
    pis_aliquota: Optional[float] = None
    cofins_cst: Optional[str] = None
    cofins_aliquota: Optional[float] = None


class DevolucaoCreate(BaseModel):
    """Payload de emissão de NF-e de devolução (mod 55, finNFe=4)."""
    model_config = ConfigDict(extra="allow")

    chave_referenciada: str = Field(min_length=44, max_length=44)
    motivo: str = Field(min_length=15)
    natureza_operacao: str = "DEVOLUCAO DE MERCADORIA"
    destinatario: DestinatarioInput
    itens: List[DevolucaoItemInput] = Field(min_length=1)


class DevolucaoPreviewResponse(BaseModel):
    """Resposta do preview via upload de XML ou chave."""
    model_config = ConfigDict(extra="allow")

    chave_referenciada: str
    natureza_operacao_sugerida: str
    destinatario: DestinatarioInput
    itens: List[DevolucaoItemInput]
    valor_total_original: float


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
