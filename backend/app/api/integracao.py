from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body
from sqlmodel import Session, select
from typing import Dict, Any, Optional, List
import uuid

from app.models.database import get_session
from app.models.usuario import Usuario
from app.models.nota import Nota
from app.schemas.nota import NotaResponse, ReceberVendaPayload
from app.api.auth import get_current_user

router = APIRouter(prefix="/integracao", tags=["Integração Externa"])

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
