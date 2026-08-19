from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body, Query
from sqlmodel import Session, select
from typing import Dict, Any, Optional, List
from datetime import timedelta, datetime
import json
import uuid

from app.models.database import get_session
from app.models.usuario import Usuario
from app.models.nota import Nota
from app.schemas.nota import NotaResponse, ReceberVendaPayload
from app.api.auth import get_current_user
from app.core.security import create_access_token
from pydantic import BaseModel

router = APIRouter(prefix="/integracao", tags=["Integração Externa"])

# TTL curto pra sessão SSO — o usuário só precisa dele pra abrir a tela;
# depois a autenticação vira responsabilidade do JWT normal do app.
SSO_JWT_TTL_MINUTES = 15


class SessaoSSOResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    usuario_id: int
    redirect_url: str  # pronto pro InnoSystem colocar num <a href>


class NotaIntegracaoResponse(BaseModel):
    """Retorno enxuto pra integradores externos. Não expõe payload_enviado
    (contém dados sensíveis do certificado/SEFAZ) nem json_venda cru (grande).
    Se o integrador quiser o JSON original, chame GET /integracao/notas/{id}."""
    id: int
    modelo: str
    status: str
    chave_acesso: Optional[str] = None
    numero: Optional[int] = None
    serie: Optional[int] = None
    valor_total: float
    empresa_id: Optional[int] = None
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None
    criado_em: datetime
    atualizado_em: datetime
    motivo_rejeicao: Optional[str] = None
    codigo_status: Optional[str] = None


class NotaIntegracaoDetalhe(NotaIntegracaoResponse):
    """Detalhe completo — inclui json_venda original e o retorno bruto da ACBr."""
    json_venda: Optional[Dict[str, Any]] = None
    resposta_integradora: Optional[Dict[str, Any]] = None


def _parse_json_safe(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _extrair_rejeicao(resposta_json: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Extrai motivo/cStat da resposta da ACBr — mesma lógica do frontend
    (autorizacao.motivo_status / codigo_status), pra o integrador não precisar
    reimplementar o parsing."""
    if not resposta_json:
        return {"motivo": None, "codigo": None}
    aut = resposta_json.get("autorizacao") or {}
    codigo = aut.get("codigo_status") or resposta_json.get("codigo_status")
    motivo = aut.get("motivo_status") or resposta_json.get("motivo_status")
    if not motivo:
        err = resposta_json.get("error")
        if isinstance(err, dict):
            motivo = err.get("message")
    if not motivo:
        motivo = resposta_json.get("motivo") or resposta_json.get("mensagem") or resposta_json.get("erro")
    return {"motivo": motivo, "codigo": str(codigo) if codigo is not None else None}


def _nota_para_response(nota: Nota, incluir_detalhe: bool = False) -> Dict[str, Any]:
    resposta = _parse_json_safe(nota.resposta_integradora)
    rej = _extrair_rejeicao(resposta)
    base = {
        "id": nota.id,
        "modelo": nota.modelo,
        "status": nota.status,
        "chave_acesso": nota.chave_acesso,
        "numero": nota.numero,
        "serie": nota.serie,
        "valor_total": nota.valor_total,
        "empresa_id": nota.empresa_id,
        "xml_url": nota.xml_url,
        "pdf_url": nota.pdf_url,
        "criado_em": nota.criado_em,
        "atualizado_em": nota.atualizado_em,
        "motivo_rejeicao": rej["motivo"],
        "codigo_status": rej["codigo"],
    }
    if incluir_detalhe:
        base["json_venda"] = _parse_json_safe(nota.json_venda)
        base["resposta_integradora"] = resposta
    return base

async def get_user_by_api_key(x_api_key: Optional[str] = Header(None), session: Session = Depends(get_session)) -> Usuario:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-API-Key é obrigatório para integração.")
        
    usuario = session.exec(select(Usuario).where(Usuario.token_integracao == x_api_key)).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="X-API-Key inválida ou usuário não encontrado.")
    
    if not usuario.ativo:
        raise HTTPException(status_code=403, detail="Usuário inativo.")
        
    return usuario

@router.post("/receber-venda", response_model=NotaResponse)
async def receber_venda_externa(
    payload: ReceberVendaPayload = Body(
        ...,
        examples=[{
            "cliente": {
                "nome": "Consumidor Exemplo",
                "cpf": "12345678909"
            },
            "itens": [
                {
                    "codigo": "JOIA001",
                    "nome": "Anel de Prata Solitário",
                    "quantidade": 1,
                    "valor_unitario": 150,
                    "unidade": "UN"
                },
                {
                    "codigo": "JOIA002",
                    "nome": "Brinco Ouro 18k Argola",
                    "quantidade": 2,
                    "valor_unitario": 450,
                    "unidade": "PR"
                }
            ],
            "desconto": 50,
            "pagamentos": [
                {"meio_pagamento": "17", "valor": 1000}
            ]
        }]
    ),
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session)
):
    """
    Endpoint para sistemas externos enviarem os dados de uma venda.
    Isso gera um rascunho de nota fiscal no InnoFiscal.

    Formato canônico (mesmo enviado pelo InnoSystem): cliente + itens (código/nome/
    quantidade/valor_unitario/unidade) + desconto + pagamentos. O valor_total é
    calculado no servidor a partir dos itens - desconto.
    """
    subtotal = sum(item.quantidade * item.valor_unitario for item in payload.itens)
    valor_total = subtotal - payload.desconto

    nova_nota = Nota(
        usuario_id=usuario.id,
        empresa_id=None,  # Será preenchido quando o usuário processar o rascunho na UI
        status="rascunho",
        json_venda=payload.model_dump_json(),
        valor_total=valor_total,
        modelo="65"  # Padrão para vendas (NFC-e)
    )

    session.add(nova_nota)
    session.commit()
    session.refresh(nova_nota)

    return nova_nota

@router.get("/rascunhos", response_model=List[NotaResponse])
async def listar_rascunhos(
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Lista todos os rascunhos de notas fiscais recebidos via integração
    (status="rascunho", ordenados por data de criação decrescente).
    """
    rascunhos = session.exec(
        select(Nota)
        .where(Nota.usuario_id == current_user.id)
        .where(Nota.status == "rascunho")
        .order_by(Nota.criado_em.desc())
    ).all()
    return rascunhos


@router.get("/rascunhos/{rascunho_id}", response_model=NotaResponse)
async def obter_rascunho(
    rascunho_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna os detalhes de um rascunho específico.
    """
    rascunho = session.exec(
        select(Nota)
        .where(Nota.id == rascunho_id)
        .where(Nota.usuario_id == current_user.id)
    ).first()

    if not rascunho:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")

    return rascunho


# ---------------------------------------------------------------------------
# Consulta de notas por Token de Integração (X-API-Key)
# ---------------------------------------------------------------------------

@router.get("/notas", response_model=List[NotaIntegracaoResponse])
async def listar_notas_integracao(
    status: Optional[str] = Query(None, description="Filtra por status: rascunho, processando, autorizada, rejeitada, cancelada"),
    modelo: Optional[str] = Query(None, description="Filtra por modelo: 55 (NF-e) ou 65 (NFC-e)"),
    empresa_id: Optional[int] = Query(None, description="Filtra por empresa emissora"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Lista todas as notas do usuário identificado pelo X-API-Key, com filtros
    opcionais. Retorna status, chave, valores, motivo de rejeição (extraído da
    resposta da SEFAZ) e URLs de XML/PDF. Ordenado por criado_em desc.
    """
    query = select(Nota).where(Nota.usuario_id == usuario.id)
    if status:
        query = query.where(Nota.status == status)
    if modelo:
        query = query.where(Nota.modelo == modelo)
    if empresa_id is not None:
        query = query.where(Nota.empresa_id == empresa_id)
    query = query.order_by(Nota.criado_em.desc()).offset(offset).limit(limit)

    notas = session.exec(query).all()
    return [_nota_para_response(n) for n in notas]


@router.get("/notas/{nota_id}", response_model=NotaIntegracaoDetalhe)
async def obter_nota_integracao(
    nota_id: int,
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Retorna o detalhe completo de uma nota — incluindo json_venda original e a
    resposta bruta da ACBr — filtrado pelo usuário dono do X-API-Key.
    """
    nota = session.exec(
        select(Nota)
        .where(Nota.id == nota_id)
        .where(Nota.usuario_id == usuario.id)
    ).first()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return _nota_para_response(nota, incluir_detalhe=True)


# ---------------------------------------------------------------------------
# SSO por Token de Integração → JWT curto
# ---------------------------------------------------------------------------

@router.post("/sessao", response_model=SessaoSSOResponse)
async def criar_sessao_sso(
    rascunho_id: Optional[int] = Query(None, description="Se informado, a URL de redirect já abre esse rascunho."),
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Troca o X-API-Key (Token de Integração) por um JWT de curta duração
    (15 minutos). O InnoSystem chama este endpoint do servidor dele — o token
    de integração NUNCA vai pro browser. O JWT retornado pode ser usado no
    frontend do InnoFiscal via `/sso?token=<jwt>[&rascunho=<id>]`.

    Segurança:
    - `access_token` tem `origin=integracao` no claim (auditável)
    - TTL de 15min limita janela de exposição
    - Se `rascunho_id` for informado, é validado como pertencente ao usuário
    """
    if rascunho_id is not None:
        pertence = session.exec(
            select(Nota.id)
            .where(Nota.id == rascunho_id)
            .where(Nota.usuario_id == usuario.id)
        ).first()
        if not pertence:
            raise HTTPException(status_code=404, detail="Rascunho não pertence ao usuário do token.")

    ttl = timedelta(minutes=SSO_JWT_TTL_MINUTES)
    token = create_access_token(
        data={"sub": usuario.email, "origin": "integracao"},
        expires_delta=ttl,
    )

    redirect = f"/sso?token={token}"
    if rascunho_id is not None:
        redirect += f"&rascunho={rascunho_id}"

    return SessaoSSOResponse(
        access_token=token,
        expires_in=int(ttl.total_seconds()),
        usuario_id=usuario.id,
        redirect_url=redirect,
    )
