from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from typing import Dict, Any, Optional, List, Tuple
from datetime import timedelta, datetime
import io
import json
import uuid

from app.models.database import get_session
from app.models.usuario import Usuario
from app.models.nota import Nota
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.schemas.nota import NotaResponse, ReceberVendaPayload
from app.api.auth import get_current_user
from app.core.security import create_access_token
from app.services.acbr_api import ACBrAPIService
from pydantic import BaseModel, Field

router = APIRouter(prefix="/integracao", tags=["Integração Externa"])

# TTL curto pra sessão SSO — o usuário só precisa dele pra abrir a tela;
# depois a autenticação vira responsabilidade do JWT normal do app.
SSO_JWT_TTL_MINUTES = 15

# cStats de denegação — SEFAZ consumiu o nNF mas recusa autorização
# permanentemente. NÃO reenviar (nNF já queimado); próxima nota segue nNF+1.
# 110 = uso denegado; 301 = irregularidade fiscal do emitente;
# 302 = irregularidade fiscal do destinatário.
CSTAT_DENEGACAO = {"110", "301", "302"}

# Status que travam a fila de nova emissão (nNF ainda não consumido pela SEFAZ,
# operador precisa corrigir/inutilizar/consultar antes da próxima). Denegada NÃO
# trava — consumiu o nNF e a fila segue.
# - rejeitada: SEFAZ rejeitou explicitamente; corrigir e reenviar OU inutilizar.
# - pendente_consulta: timeout/erro de comunicação; status real desconhecido,
#   precisa consultar SEFAZ por chave antes de decidir o próximo passo.
STATUS_BLOQUEIA_FILA = {"rejeitada", "pendente_consulta"}


def _eh_denegacao(codigo_status: Optional[Any]) -> bool:
    """True se o cStat da SEFAZ indica denegação (nNF consumido, sem reenvio)."""
    if codigo_status is None:
        return False
    return str(codigo_status).strip() in CSTAT_DENEGACAO


def _eh_timeout_acbr(resposta: Optional[Dict[str, Any]]) -> bool:
    """True quando ACBr/SEFAZ NÃO deu resposta definitiva no envio.

    O service `ACBrAPIService.transmitir_*` devolve `("processando", {"erro": "..."})`
    em três casos:
    - Falha de autenticação Keycloak (envio nem começou)
    - Erro de comunicação HTTP (timeout, TLS, DNS) — SEFAZ pode ter recebido ou não
    - Exception parseando o JSON de resposta

    Nesses cenários o status real da nota é INCERTO — não dá pra assumir rejeitada
    (a SEFAZ pode ter autorizado e a resposta se perdeu no caminho). O InnoFiscal
    marca como `pendente_consulta` e o InnoSystem chama `POST /notas/{id}/consultar`
    pra resolver.

    Diferente de: `("processando", {"id": "nfe_...", "status": "processando"})` que
    é fila assíncrona legítima da NF-e — resposta tem id, sem chave `erro` — o
    polling normal via GET resolve.
    """
    if resposta is None:
        return True
    return bool(resposta.get("erro"))


def _verificar_pendencia_fila_fiscal(usuario: Usuario, session: Session) -> None:
    """Recusa nova emissão se existe nota anterior rejeitada do mesmo usuário.

    Regra fiscal: `nNF` é sequencial ascendente por (empresa, modelo, série).
    Se a última nota foi rejeitada e o operador emitir a próxima antes de
    corrigir/inutilizar, o `nNF` rejeitado fica pulado — furo de sequência
    que a SEFAZ vai questionar.

    Denegada NÃO bloqueia (nNF consumido, próxima segue nNF+1).
    Levanta HTTP 422 com payload `ERRO_INTERNO_REGRA_FISCAL /
    PENDENCIA_NOTA_ANTERIOR` apontando a nota que precisa ser resolvida.
    """
    pendente = session.exec(
        select(Nota)
        .where(Nota.usuario_id == usuario.id)
        .where(Nota.status.in_(STATUS_BLOQUEIA_FILA))
        .order_by(Nota.criado_em.desc())
    ).first()
    if not pendente:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "sucesso": False,
            "tipo_erro": "ERRO_INTERNO_REGRA_FISCAL",
            "codigo_erro": "PENDENCIA_NOTA_ANTERIOR",
            "mensagem": (
                f"Não foi possível emitir a nova nota fiscal. Existe uma nota "
                f"fiscal anterior (ID: {pendente.id}, "
                f"Número: {pendente.numero}) que foi rejeitada pela SEFAZ e "
                f"precisa ser corrigida/retransmitida antes de prosseguir."
            ),
            "detalhes": {
                "id_nota_pendente": pendente.id,
                "numero_nota_pendente": pendente.numero,
                "status_atual": pendente.status,
            },
        },
    )


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
    # Devolução (finNFe=4). Nulos em emissão normal.
    finalidade: Optional[int] = None  # 1=normal, 2=complementar, 3=ajuste, 4=devolução
    nota_referenciada_chave: Optional[str] = None
    nota_referenciada_id: Optional[int] = None
    natureza_operacao: Optional[str] = None


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


def _urls_integracao(nota: Nota) -> Tuple[Optional[str], Optional[str]]:
    """URLs canônicas de download via integração (X-API-Key).

    Só existem quando a nota já foi transmitida (tem `acbr_id`). Retorna paths
    relativos — o cliente resolve com o host da API que está usando (dev/prod).
    """
    if not nota.acbr_id:
        return None, None
    return (
        f"/integracao/notas/{nota.id}/xml",
        f"/integracao/notas/{nota.id}/pdf",
    )


def _nota_para_response(nota: Nota, incluir_detalhe: bool = False) -> Dict[str, Any]:
    resposta = _parse_json_safe(nota.resposta_integradora)
    # motivo/código só fazem sentido em status de erro. Em cancelada/autorizada
    # a `resposta_integradora` guarda o retorno do último evento (ex: cStat 135
    # "Evento registrado" pro cancelamento) — não é rejeição, mas o InnoSystem
    # interpretava como se fosse.
    _STATUS_COM_ERRO = {"rejeitada", "denegada", "pendente_consulta"}
    rej = _extrair_rejeicao(resposta) if nota.status in _STATUS_COM_ERRO else {"motivo": None, "codigo": None}
    xml_url, pdf_url = _urls_integracao(nota)
    base = {
        "id": nota.id,
        "modelo": nota.modelo,
        "status": nota.status,
        "chave_acesso": nota.chave_acesso,
        "numero": nota.numero,
        "serie": nota.serie,
        "valor_total": nota.valor_total,
        "empresa_id": nota.empresa_id,
        "xml_url": xml_url,
        "pdf_url": pdf_url,
        "criado_em": nota.criado_em,
        "atualizado_em": nota.atualizado_em,
        "motivo_rejeicao": rej["motivo"],
        "codigo_status": rej["codigo"],
        "finalidade": nota.finalidade,
        "nota_referenciada_chave": nota.nota_referenciada_chave,
        "nota_referenciada_id": nota.nota_referenciada_id,
        "natureza_operacao": nota.natureza_operacao,
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

    Trava de fila: se o usuário tem nota anterior com status `rejeitada`, este
    endpoint responde HTTP 422 (`PENDENCIA_NOTA_ANTERIOR`) — o InnoSystem precisa
    corrigir/reenviar a pendente antes de mandar a próxima venda.

    Trava master: se TODAS as empresas do usuário estão bloqueadas/deletadas pelo
    admin, retorna 403 — evita gerar rascunho órfão que nunca vai ser processado.
    """
    # Guard master: pelo menos uma empresa ativa (não bloqueada, não deletada)
    empresa_ativa = session.exec(
        select(Empresa).where(
            Empresa.usuario_id == usuario.id,
            Empresa.bloqueada == False,  # noqa: E712
            Empresa.deletada_em.is_(None),
        )
    ).first()
    if not empresa_ativa:
        raise HTTPException(
            status_code=403,
            detail="Nenhuma empresa ativa disponível para emissão — contate o suporte.",
        )

    _verificar_pendencia_fila_fiscal(usuario, session)

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


@router.post("/reenviar/{nota_id}", response_model=NotaResponse)
async def reenviar_nota_via_integracao(
    nota_id: int,
    payload: ReceberVendaPayload = Body(
        ...,
        description=(
            "JSON de venda corrigido — mesmo shape do POST /receber-venda. "
            "Substitui o json_venda salvo antes de retransmitir."
        ),
    ),
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """Reenvia uma nota REJEITADA reaproveitando o mesmo `nNF` e `serie`.

    Uso: quando a SEFAZ rejeitou uma nota e o InnoSystem já corrigiu o
    cadastro (cliente, produto, valor). Manda o JSON corrigido apontando pra
    nota rejeitada e o InnoFiscal retransmite mantendo a numeração.

    Regras:
    - `nota_id` deve pertencer ao usuário do X-API-Key.
    - Nota precisa estar com `status="rejeitada"`.
    - Nota precisa ter `numero` e `empresa_id` já reservados (só quem transmitiu
      pelo menos uma vez tem isso — rascunhos puros não são reenviáveis).
    - Retransmite direto (não vira rascunho — o InnoSystem já validou os dados).
    """
    # 1. Carregar nota e validar
    nota = _carregar_nota_do_usuario(nota_id, usuario, session)
    if nota.status != "rejeitada":
        raise HTTPException(
            status_code=400,
            detail=f"Só é possível reenviar notas com status='rejeitada'. Status atual: '{nota.status}'.",
        )
    if nota.numero is None:
        raise HTTPException(
            status_code=400,
            detail="Nota rejeitada sem número reservado — impossível reenviar sem gerar furo.",
        )
    if nota.empresa_id is None:
        raise HTTPException(
            status_code=400,
            detail="Nota rejeitada sem empresa vinculada — nunca foi transmitida. Use /receber-venda.",
        )

    # 2. Carregar empresa (o usuário do X-API-Key precisa ser o dono)
    empresa = session.get(Empresa, nota.empresa_id)
    if not empresa or empresa.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Empresa da nota não encontrada.")
    if empresa.deletada_em is not None:
        raise HTTPException(status_code=410, detail="Empresa deletada.")
    if empresa.bloqueada:
        raise HTTPException(status_code=403, detail="Empresa bloqueada — contate o suporte.")

    # 3. Regra fiscal padrão da empresa
    regra = session.exec(
        select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id, RegraFiscal.padrao == True)
    ).first()
    if not regra:
        regra = session.exec(
            select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id)
        ).first()
    if not regra:
        raise HTTPException(status_code=400, detail="Nenhuma regra fiscal cadastrada para a empresa.")

    # 4. Substituir json_venda pelo payload corrigido + recalcular total
    venda_data = payload.model_dump()
    v_prod = sum(float(it.get("quantidade", 0)) * float(it.get("valor_unitario", 0)) for it in venda_data.get("itens", []))
    v_desc = float(venda_data.get("desconto", 0.0))
    valor_total = round(v_prod - v_desc, 2)

    # 5. Montar payload ACBr — REUSA nNF/serie da nota original
    modelo_int = int(nota.modelo) if nota.modelo else 65
    acbr_service = ACBrAPIService()
    try:
        payload_acbr = acbr_service.montar_payload_nfce(
            empresa, regra, venda_data,
            modelo=modelo_int, numero=nota.numero, serie=nota.serie or 1,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 6. Atualizar registro (mesma nota, não cria nova)
    nota.status = "processando"
    nota.valor_total = valor_total
    nota.json_venda = json.dumps(venda_data)
    nota.payload_enviado = json.dumps(payload_acbr)
    nota.atualizado_em = datetime.utcnow()
    session.add(nota)
    session.commit()
    session.refresh(nota)

    # 7. Transmitir
    if modelo_int == 55:
        status, resposta = await acbr_service.transmitir_nfe(payload_acbr)
    else:
        status, resposta = await acbr_service.transmitir_nfce(payload_acbr)

    # 8. Tratar retorno
    nota.status = status
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()

    if status == "autorizada":
        nota.acbr_id = resposta.get("id")
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        acbr_numero = resposta.get("numero") or resposta.get("numeroNota")
        if acbr_numero is not None:
            nota.numero = acbr_numero
        acbr_serie = resposta.get("serie")
        if acbr_serie is not None:
            nota.serie = acbr_serie
        if nota.acbr_id:
            if nota.acbr_id.startswith("nfc_"):
                nota.modelo = "65"
            elif nota.acbr_id.startswith("nfe_"):
                nota.modelo = "55"
        nota.pdf_url = f"/empresas/{empresa.id}/notas/{nota.id}/pdf"
        nota.xml_url = f"/empresas/{empresa.id}/notas/{nota.id}/xml"
    elif status == "processando":
        nota.acbr_id = resposta.get("id")
        nota.chave_acesso = (
            resposta.get("chave") or resposta.get("chaveAcesso") or payload_acbr.get("referencia")
        )
        # Timeout/erro comm com ACBr: SEFAZ pode ter recebido ou não. Marca
        # pendente_consulta e trava a fila até `POST /notas/{id}/consultar` resolver.
        if _eh_timeout_acbr(resposta):
            nota.status = "pendente_consulta"
        nota.pdf_url = f"/empresas/{empresa.id}/notas/{nota.id}/pdf"
        nota.xml_url = f"/empresas/{empresa.id}/notas/{nota.id}/xml"
    else:
        # Rejeição de novo — achata motivo/cstat no topo
        aut = resposta.get("autorizacao") or {}
        err = resposta.get("error") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("motivo")
            or resposta.get("mensagem")
            or (resposta.get("erro") if isinstance(resposta.get("erro"), str) else None)
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        resposta = {**resposta, "motivo_status": motivo, "codigo_status": cstat}
        # Denegação (110/301/302) consome o nNF mas trava o reenvio — status
        # próprio pra o InnoSystem parar de tentar reenviar essa nota.
        if _eh_denegacao(cstat):
            nota.status = "denegada"
        nota.resposta_integradora = json.dumps(resposta)
        nota.acbr_id = resposta.get("id") or nota.acbr_id

    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota


# ---------------------------------------------------------------------------
# Consulta por chave — destrava `pendente_consulta` / atualiza `processando`
# ---------------------------------------------------------------------------


def _resolver_modelo_para_consulta(nota: Nota) -> int:
    """Prefixo do acbr_id vence; fallback pro campo `modelo` da nota."""
    if nota.acbr_id:
        if nota.acbr_id.startswith("nfc_"):
            return 65
        if nota.acbr_id.startswith("nfe_"):
            return 55
    return 55 if nota.modelo == "55" else 65


@router.post("/notas/{nota_id}/consultar", response_model=NotaIntegracaoResponse)
async def consultar_nota_integracao(
    nota_id: int,
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """Consulta o status real na SEFAZ pra destravar `pendente_consulta` ou finalizar `processando`.

    Uso: quando o `POST /receber-venda`/emissão retornou timeout (SEFAZ pode ter
    recebido ou não), a nota fica `pendente_consulta` e trava a fila. Este
    endpoint consulta a SEFAZ e resolve:

    - SEFAZ autorizou → `autorizada` (fila destrava, XML/PDF disponíveis)
    - SEFAZ rejeitou → `rejeitada` (corrigir + `/reenviar` ou `/inutilizar`)
    - SEFAZ denegou (cStat 110/301/302) → `denegada` (fila destrava, nNF queimado)
    - SEFAZ diz "não encontrada" → mantém `pendente_consulta` (payload nem chegou,
      pode reenviar mesmo nNF via `/reenviar`)
    - Ainda processando na fila SEFAZ (raro) → mantém `processando`

    Idempotente: chamar em nota já autorizada/rejeitada/etc devolve o estado atual
    sem consultar de novo.
    """
    nota = _carregar_nota_do_usuario(nota_id, usuario, session)

    # Estados terminais — nada a consultar
    if nota.status not in ("processando", "pendente_consulta"):
        return _nota_para_response(nota)

    identificador = nota.acbr_id or nota.chave_acesso
    if not identificador and nota.payload_enviado:
        try:
            identificador = json.loads(nota.payload_enviado).get("referencia")
        except (ValueError, TypeError):
            pass
    if not identificador:
        raise HTTPException(
            status_code=400,
            detail="Nota sem identificador (acbr_id/chave/referencia) — impossível consultar SEFAZ.",
        )

    modelo_int = _resolver_modelo_para_consulta(nota)
    acbr = ACBrAPIService()
    ok, resposta = await acbr.consultar_documento(identificador, modelo=modelo_int)

    # Sem dado útil da ACBr → mantém pendente_consulta pra próxima tentativa.
    # NÃO devolve 502 pra não travar o InnoSystem em polling agressivo.
    if not ok or _eh_timeout_acbr(resposta):
        return _nota_para_response(nota)

    acbr_status = str(resposta.get("status") or "").lower()
    aut = resposta.get("autorizacao") or {}
    cstat = aut.get("codigo_status") or resposta.get("codigo_status")

    if _eh_denegacao(cstat):
        nota.status = "denegada"
    elif acbr_status.startswith("autoriz"):
        nota.status = "autorizada"
        nota.chave_acesso = (
            resposta.get("chave") or resposta.get("chaveAcesso") or nota.chave_acesso
        )
    elif acbr_status.startswith("rejeit"):
        nota.status = "rejeitada"
    # senão: SEFAZ ainda não decidiu — deixa status como está (processando ou pendente_consulta)

    if resposta.get("id") and not nota.acbr_id:
        nota.acbr_id = resposta.get("id")
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()
    session.add(nota)
    session.commit()
    session.refresh(nota)
    return _nota_para_response(nota)


# ---------------------------------------------------------------------------
# Inutilização de UMA nota (último recurso — destrava a fila)
# ---------------------------------------------------------------------------


class InutilizarNotaRequest(BaseModel):
    """Body do POST /integracao/inutilizar/{id}."""
    justificativa: str = Field(..., min_length=15, max_length=255)


@router.post("/inutilizar/{nota_id}")
async def inutilizar_nota_integracao(
    nota_id: int,
    body: InutilizarNotaRequest,
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """Inutiliza o nNF de UMA nota rejeitada/pendente na SEFAZ — destrava a fila.

    ÚLTIMO RECURSO. A preferência é sempre reenviar com correção (`POST /reenviar/
    {id}` reusa o mesmo nNF). Só use inutilizar quando o operador DESISTIR da
    venda rejeitada — a inutilização gera lastro fiscal permanente na SEFAZ.

    Aceita: `rejeitada` (SEFAZ rejeitou explicitamente) ou `pendente_consulta`
    (timeout, mas o operador não quer arriscar reenviar). NÃO aceita autorizada
    (isso é cancelamento), denegada (nNF já consumido, nada a inutilizar) ou
    inutilizada (já inutilizada).

    Após sucesso, a fila destrava (status vira `inutilizada`, sai do
    `STATUS_BLOQUEIA_FILA`).
    """
    nota = _carregar_nota_do_usuario(nota_id, usuario, session)

    if nota.status not in ("rejeitada", "pendente_consulta"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Só notas 'rejeitada' ou 'pendente_consulta' podem ser inutilizadas. "
                f"Status atual: '{nota.status}'."
            ),
        )
    if nota.numero is None:
        raise HTTPException(
            status_code=400,
            detail="Nota sem número reservado — nada a inutilizar na SEFAZ.",
        )
    if nota.empresa_id is None:
        raise HTTPException(
            status_code=400,
            detail="Nota sem empresa vinculada — impossível inutilizar (sem CNPJ).",
        )

    empresa = session.get(Empresa, nota.empresa_id)
    if not empresa or empresa.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Empresa da nota não encontrada.")
    if empresa.deletada_em is not None:
        raise HTTPException(status_code=410, detail="Empresa deletada.")
    if empresa.bloqueada:
        raise HTTPException(status_code=403, detail="Empresa bloqueada — contate o suporte.")

    modelo_int = 55 if nota.modelo == "55" else 65
    ano = (nota.criado_em or datetime.utcnow()).year

    acbr = ACBrAPIService()
    ok, resposta = await acbr.inutilizar_faixa(
        cnpj=empresa.cnpj,
        ano=ano,
        serie=nota.serie or 1,
        numero_inicial=nota.numero,
        numero_final=nota.numero,
        justificativa=body.justificativa,
        modelo=modelo_int,
    )

    if not ok:
        aut = resposta.get("autorizacao") or {}
        err = resposta.get("error") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("erro")
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        prefixo = f"cStat {cstat}: " if cstat else ""
        raise HTTPException(
            status_code=400,
            detail=f"SEFAZ recusou inutilização: {prefixo}{motivo}",
        )

    nota.status = "inutilizada"
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()
    session.add(nota)
    session.commit()
    session.refresh(nota)

    return {
        "sucesso": True,
        "nota_id": nota.id,
        "numero_inutilizado": nota.numero,
        "modelo": nota.modelo,
        "serie": nota.serie,
        "resposta_sefaz": resposta,
    }


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
    ids: Optional[str] = Query(None, description="Lista de ids separados por vírgula (ex: 1,2,3). Ignora demais filtros de listagem."),
    status: Optional[str] = Query(None, description="Filtra por status: rascunho, processando, autorizada, rejeitada, cancelada"),
    modelo: Optional[str] = Query(None, description="Filtra por modelo: 55 (NF-e) ou 65 (NFC-e)"),
    empresa_id: Optional[int] = Query(None, description="Filtra por empresa emissora"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Lista notas do usuário identificado pelo X-API-Key.

    Uso comum:
    - `?ids=1,2,3` → polling em lote de ids conhecidos (ex: rascunhos que
      viraram nota autorizada). Retorna só os que existem e pertencem ao
      usuário; máximo 200 ids por chamada.
    - `?status=autorizada&limit=50` → notas recém autorizadas.

    Retorna status atual, chave, número, série, motivo de rejeição e URLs
    de XML/PDF. Ordenado por criado_em desc.
    """
    query = select(Nota).where(Nota.usuario_id == usuario.id)

    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Parâmetro 'ids' deve ser uma lista de inteiros separados por vírgula.")
        if len(id_list) > 200:
            raise HTTPException(status_code=400, detail="Máximo de 200 ids por chamada.")
        if not id_list:
            return []
        query = query.where(Nota.id.in_(id_list)).order_by(Nota.criado_em.desc())
    else:
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


def _resolver_modelo_e_id_acbr(nota: Nota) -> Tuple[int, str]:
    """Resolve (modelo, acbr_id) pra baixar XML/PDF na ACBr.

    Mesma regra da rota interna (`app/api/notas.py`): o prefixo do `acbr_id`
    é fonte de verdade pro modelo (nfc_ = 65, nfe_ = 55). Levanta 400 se a
    nota ainda não tem `acbr_id` (rascunho / não transmitida).
    """
    if not nota.acbr_id:
        raise HTTPException(
            status_code=400,
            detail="Nota não possui id da ACBr — arquivo indisponível (nota ainda não foi transmitida).",
        )
    if nota.acbr_id.startswith("nfc_"):
        return 65, nota.acbr_id
    if nota.acbr_id.startswith("nfe_"):
        return 55, nota.acbr_id
    return (65 if nota.modelo == "65" else 55), nota.acbr_id


def _carregar_nota_do_usuario(nota_id: int, usuario: Usuario, session: Session) -> Nota:
    nota = session.exec(
        select(Nota)
        .where(Nota.id == nota_id)
        .where(Nota.usuario_id == usuario.id)
    ).first()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return nota


@router.get("/notas/{nota_id}/xml")
async def baixar_xml_integracao(
    nota_id: int,
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Baixa o XML autorizado da nota (modelo 55 ou 65), autenticado por X-API-Key.

    Retorna `application/xml` como attachment com o nome `{chave_acesso}.xml`.
    Requer que a nota já tenha sido transmitida (status = autorizada/cancelada
    e `acbr_id` preenchido).
    """
    nota = _carregar_nota_do_usuario(nota_id, usuario, session)
    modelo, acbr_id = _resolver_modelo_e_id_acbr(nota)

    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.baixar_xml(acbr_id, modelo=modelo)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar XML na ACBr: {res}")

    chave = nota.chave_acesso or acbr_id
    return StreamingResponse(
        io.BytesIO(res),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={chave}.xml"},
    )


@router.get("/notas/{nota_id}/pdf")
async def baixar_pdf_integracao(
    nota_id: int,
    usuario: Usuario = Depends(get_user_by_api_key),
    session: Session = Depends(get_session),
):
    """
    Baixa o DANFE (PDF) da nota (modelo 55 ou 65), autenticado por X-API-Key.

    Retorna `application/pdf` inline com o nome `{chave_acesso}.pdf`.
    Requer que a nota já tenha sido transmitida.
    """
    nota = _carregar_nota_do_usuario(nota_id, usuario, session)
    modelo, acbr_id = _resolver_modelo_e_id_acbr(nota)

    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.baixar_pdf(acbr_id, modelo=modelo)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar DANFE na ACBr: {res}")

    chave = nota.chave_acesso or acbr_id
    return StreamingResponse(
        io.BytesIO(res),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={chave}.pdf"},
    )


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
