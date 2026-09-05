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
    # Override do proximo nNF (ex: operador viu o preview e quer emitir com outro
    # numero). NULL/0 = usa MAX+1 normal.
    numero_override: Optional[int] = Field(default=None, ge=1)

class NotaResponse(NotaBase):
    id: int
    empresa_id: Optional[int] = None
    criado_em: datetime
    atualizado_em: datetime

class NotaCancelar(BaseModel):
    justificativa: str

    class Config:
        orm_mode = True


class EnderecoCliente(BaseModel):
    """Endereço do destinatário (grupo <enderDest> da NF-e).

    Obrigatório em NF-e mod 55 (SEFAZ rejeita com cStat 726 se faltar). Em NFC-e
    mod 65 é opcional — consumidor anônimo omite o bloco inteiro.
    """
    model_config = ConfigDict(extra="allow")

    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None  # 2 letras (ex: "MG")
    cep: Optional[str] = None  # 8 dígitos
    codigo_municipio: Optional[str] = None  # IBGE 7 dígitos; se omitido, backend usa o do emitente


class ReceberVendaCliente(BaseModel):
    # Aceita campos extras (email, telefone, etc.) preservados no json_venda.
    model_config = ConfigDict(extra="allow")

    nome: str
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    endereco: Optional[EnderecoCliente] = None


class ReceberVendaItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    codigo: Optional[str] = None
    nome: str
    quantidade: float = Field(gt=0)
    valor_unitario: float = Field(ge=0)
    unidade: str = "UN"
    # NCM opcional. Se vier, o InnoFiscal usa o NCM do produto; se omitir,
    # cai no `ncm_padrao` da regra fiscal da empresa. Aceita com ou sem
    # formatação — só os dígitos são mandados pra SEFAZ (limite 8).
    ncm: Optional[str] = None


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
    # IPI (só se a nota original destacou — Regime Normal com IPI)
    ipi_cst: Optional[str] = None
    ipi_aliquota: Optional[float] = None
    ipi_enquadramento: Optional[str] = None  # cEnq (default "999")


class TransporteInput(BaseModel):
    """Dados de transporte da NF-e (grupo <transp> na SEFAZ).

    - `mod_frete`: 0=por conta do emitente (CIF), 1=por conta do destinatário (FOB),
      2=por conta de terceiros, 3=próprio do remetente, 4=próprio do destinatário,
      9=sem frete (default).
    - Transportador, veículo e volume são opcionais; só entram no XML se preenchidos.
    """
    model_config = ConfigDict(extra="allow")

    mod_frete: int = 9

    # Transportador
    transportador_cnpj: Optional[str] = None
    transportador_cpf: Optional[str] = None
    transportador_nome: Optional[str] = None
    transportador_ie: Optional[str] = None
    transportador_endereco: Optional[str] = None
    transportador_municipio: Optional[str] = None
    transportador_uf: Optional[str] = None

    # Veículo
    veiculo_placa: Optional[str] = None
    veiculo_uf: Optional[str] = None
    veiculo_rntc: Optional[str] = None

    # Volume
    volume_qtd: Optional[int] = None
    volume_especie: Optional[str] = None  # "CX", "PC", etc
    volume_peso_liquido: Optional[float] = None
    volume_peso_bruto: Optional[float] = None


class DevolucaoCreate(BaseModel):
    """Payload de emissão de NF-e de devolução (mod 55, finNFe=4)."""
    model_config = ConfigDict(extra="allow")

    chave_referenciada: str = Field(min_length=44, max_length=44)
    motivo: str = Field(min_length=15)
    natureza_operacao: str = "DEVOLUCAO DE MERCADORIA"
    destinatario: DestinatarioInput
    itens: List[DevolucaoItemInput] = Field(min_length=1)
    transporte: Optional[TransporteInput] = None


class DevolucaoPreviewResponse(BaseModel):
    """Resposta do preview via upload de XML ou chave."""
    model_config = ConfigDict(extra="allow")

    chave_referenciada: str
    natureza_operacao_sugerida: str
    destinatario: DestinatarioInput
    itens: List[DevolucaoItemInput]
    valor_total_original: float


class DestinatarioReenvio(BaseModel):
    """Dados de destinatário atualizáveis no reenvio de nota rejeitada.

    Todos opcionais — o que vier substitui o campo correspondente no json_venda
    salvo; o que não vier mantém o valor original.
    """
    model_config = ConfigDict(extra="allow")

    nome: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    cep: Optional[str] = None
    codigo_municipio: Optional[str] = None


class NotaReenviar(BaseModel):
    """Body opcional para POST /notas/{id}/reenviar.

    Se vier `destinatario`, seus campos preenchidos sobrescrevem o
    `cliente`/`cliente.endereco` do json_venda salvo antes da retransmissão.
    Se o body inteiro for omitido, o payload original é retransmitido igual.
    """
    model_config = ConfigDict(extra="allow")

    destinatario: Optional[DestinatarioReenvio] = None


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
