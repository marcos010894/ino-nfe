"""Central de Documentos v3 — endpoints do contador + alertas.

Escopo:
- `GET/PUT /empresas/{id}/contador` — config do modal "Dados do contador" (V3.6)
- `POST /empresas/{id}/contador/enviar` — dispara email agora (V3.7)
- `GET /empresas/{id}/contador/log` — histórico de envios (últimos 12)
- `GET /empresas/{id}/alertas` — banner "N itens precisam de atenção"

Auth = mesmo padrão de `empresas.py` (JWT + `_verificar_empresa`).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from app.api.auth import get_current_user
from app.core.config import settings
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.envio_contador_log import EnvioContadorLog
from app.models.nota import Nota
from app.models.usuario import Usuario
from app.services.envio_contador import (
    ContadorNaoConfiguradoError,
    SmtpNaoConfiguradoError,
    enviar_para_contador,
)

router = APIRouter(prefix="/empresas/{empresa_id}", tags=["Central de Documentos v3"])


def _verificar_empresa(empresa_id: int, session: Session, current_user: Usuario) -> Empresa:
    """Mesma regra do notas.py — admin enxerga tudo."""
    empresa = session.get(Empresa, empresa_id)
    dono_ok = empresa and (empresa.usuario_id == current_user.id or current_user.is_admin)
    if not empresa or not dono_ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    if empresa.deletada_em is not None:
        raise HTTPException(status_code=410, detail="Empresa deletada.")
    return empresa


# ---------------------------------------------------------------------------
# Config do contador
# ---------------------------------------------------------------------------


class ContadorConfigResponse(BaseModel):
    nome_contador: Optional[str] = None
    email_contador: Optional[str] = None
    email_cc_contador: Optional[str] = None
    dia_envio_contador: Optional[int] = None
    envio_automatico_contador: bool = False
    assunto_email_contador: Optional[str] = None
    mensagem_email_contador: Optional[str] = None
    # Diagnóstico pra UI mostrar se dá pra ativar automático
    smtp_configurado: bool = False


class ContadorConfigUpdate(BaseModel):
    nome_contador: Optional[str] = Field(default=None, max_length=200)
    email_contador: Optional[EmailStr] = None
    email_cc_contador: Optional[EmailStr] = None
    # 1..28 pra sobreviver a fevereiro. None desliga automático.
    dia_envio_contador: Optional[int] = Field(default=None, ge=1, le=28)
    envio_automatico_contador: Optional[bool] = None
    assunto_email_contador: Optional[str] = Field(default=None, max_length=200)
    mensagem_email_contador: Optional[str] = Field(default=None, max_length=4000)


def _serializar_config(empresa: Empresa) -> ContadorConfigResponse:
    return ContadorConfigResponse(
        nome_contador=empresa.nome_contador,
        email_contador=empresa.email_contador,
        email_cc_contador=empresa.email_cc_contador,
        dia_envio_contador=empresa.dia_envio_contador,
        envio_automatico_contador=empresa.envio_automatico_contador,
        assunto_email_contador=empresa.assunto_email_contador,
        mensagem_email_contador=empresa.mensagem_email_contador,
        smtp_configurado=bool(settings.smtp_host and settings.smtp_user and settings.smtp_password),
    )


@router.get("/contador", response_model=ContadorConfigResponse)
def obter_config_contador(
    empresa_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    empresa = _verificar_empresa(empresa_id, session, current_user)
    return _serializar_config(empresa)


@router.put("/contador", response_model=ContadorConfigResponse)
def atualizar_config_contador(
    empresa_id: int,
    payload: ContadorConfigUpdate,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    empresa = _verificar_empresa(empresa_id, session, current_user)
    dados = payload.dict(exclude_unset=True)

    # Regra: pra ligar envio automático precisa ter (email + dia + smtp).
    quer_ativar = dados.get("envio_automatico_contador") is True
    email_final = dados.get("email_contador", empresa.email_contador)
    dia_final = dados.get("dia_envio_contador", empresa.dia_envio_contador)
    if quer_ativar:
        if not email_final:
            raise HTTPException(status_code=400, detail="Preencha o e-mail do contador antes de ativar envio automático.")
        if not dia_final:
            raise HTTPException(status_code=400, detail="Escolha um dia (1-28) antes de ativar envio automático.")
        if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
            raise HTTPException(status_code=400, detail="SMTP do InnoFiscal não configurado — avise o suporte.")

    for k, v in dados.items():
        setattr(empresa, k, v)
    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    return _serializar_config(empresa)


# ---------------------------------------------------------------------------
# Envio manual
# ---------------------------------------------------------------------------


class EnviarContadorBody(BaseModel):
    """Período opcional — se não vier, usa mês atual até agora."""
    data_inicio: Optional[str] = None  # YYYY-MM-DD
    data_fim: Optional[str] = None     # YYYY-MM-DD


def _parse_data(s: Optional[str], *, fim: bool = False) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        if fim:
            d = d.replace(hour=23, minute=59, second=59)
        return d
    except ValueError:
        return None


@router.post("/contador/enviar")
async def enviar_contador_manual(
    empresa_id: int,
    body: EnviarContadorBody = Body(default_factory=EnviarContadorBody),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Dispara envio pro contador agora (manual). Permite qualquer período."""
    empresa = _verificar_empresa(empresa_id, session, current_user)

    inicio = _parse_data(body.data_inicio)
    fim = _parse_data(body.data_fim, fim=True)
    if inicio is None:
        agora = datetime.utcnow()
        inicio = datetime(agora.year, agora.month, 1)
    if fim is None:
        fim = datetime.utcnow()
    if fim < inicio:
        raise HTTPException(status_code=400, detail="data_fim menor que data_inicio.")

    try:
        r = await enviar_para_contador(
            session=session,
            empresa=empresa,
            inicio=inicio,
            fim=fim,
            disparado_por="manual",
        )
    except ContadorNaoConfiguradoError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SmtpNaoConfiguradoError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")

    return {
        "ok": True,
        "periodo_ref": r.periodo_ref,
        "destinatarios": r.destinatarios,
        "qtd_notas": r.qtd_notas,
    }


@router.get("/contador/log")
def listar_log_envios(
    empresa_id: int,
    limit: int = Query(12, ge=1, le=60),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Últimos envios pro contador (default 12 — 1 ano)."""
    _verificar_empresa(empresa_id, session, current_user)
    rows = session.exec(
        select(EnvioContadorLog)
        .where(EnvioContadorLog.empresa_id == empresa_id)
        .order_by(EnvioContadorLog.enviado_em.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "periodo_ref": r.periodo_ref,
            "enviado_em": r.enviado_em.isoformat() if r.enviado_em else None,
            "destinatarios": r.destinatarios,
            "qtd_notas": r.qtd_notas,
            "ok": r.ok,
            "erro": r.erro,
            "disparado_por": r.disparado_por,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Alertas (banner "N itens precisam de atenção")
# ---------------------------------------------------------------------------


@router.get("/alertas")
def obter_alertas(
    empresa_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Feed do banner do topo da Central v3.

    Cada item tem `tipo` (rejeitada|aguardando|inutilizar|cert_vencendo),
    `severidade` (info|warn|erro), `label` (texto pronto) e `count` (inteiro
    quando aplicável). Frontend só renderiza — regra fica aqui."""
    empresa = _verificar_empresa(empresa_id, session, current_user)
    agora = datetime.utcnow()
    inicio_mes = datetime(agora.year, agora.month, 1)

    # Rejeitadas do mês (ainda não reprocessadas nem inutilizadas)
    rejeitadas = session.exec(
        select(Nota).where(
            Nota.empresa_id == empresa_id,
            Nota.status == "rejeitada",
            Nota.criado_em >= inicio_mes,
        )
    ).all()

    # Aguardando SEFAZ (pendente_consulta / processando)
    aguardando = session.exec(
        select(Nota).where(
            Nota.empresa_id == empresa_id,
            Nota.status.in_(["pendente_consulta", "processando"]),  # type: ignore[attr-defined]
        )
    ).all()

    # Numeração sem uso — heurística: MAX(numero) por (modelo,serie) menos qtd de notas
    # cria a "quantidade em falta" que poderia virar inutilização. Deixa cru — o
    # dono clica pra ver detalhe (V3 já tem tela de inutilizadas).
    faltas: dict[tuple[int, int], int] = {}
    todas = session.exec(
        select(Nota).where(
            Nota.empresa_id == empresa_id,
            Nota.numero.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    por_grupo: dict[tuple[str, int], list[int]] = {}
    for n in todas:
        if n.numero is None:
            continue
        chave = (n.modelo or "65", n.serie or 1)
        por_grupo.setdefault(chave, []).append(n.numero)
    for (modelo, serie), nums in por_grupo.items():
        max_num = max(nums)
        usados = {x for x in nums}
        faltando = [x for x in range(1, max_num + 1) if x not in usados]
        if faltando:
            faltas[(int(modelo) if modelo.isdigit() else 65, serie)] = len(faltando)
    qtd_faltas_total = sum(faltas.values())

    alertas: list[dict] = []
    if rejeitadas:
        alertas.append({
            "tipo": "rejeitada",
            "severidade": "erro",
            "count": len(rejeitadas),
            "label": f"{len(rejeitadas)} nota{'s' if len(rejeitadas) != 1 else ''} rejeitada{'s' if len(rejeitadas) != 1 else ''} pela SEFAZ",
        })
    if aguardando:
        alertas.append({
            "tipo": "aguardando",
            "severidade": "warn",
            "count": len(aguardando),
            "label": f"{len(aguardando)} nota{'s' if len(aguardando) != 1 else ''} aguardando resposta da SEFAZ",
        })
    if qtd_faltas_total:
        alertas.append({
            "tipo": "inutilizar",
            "severidade": "info",
            "count": qtd_faltas_total,
            "label": f"{qtd_faltas_total} número{'s' if qtd_faltas_total != 1 else ''} sem uso para inutilizar",
        })

    # Certificado vencendo
    if empresa.certificado_vencimento:
        # certificado_vencimento pode vir naive ou tz-aware — normalizar pra naive
        venc = empresa.certificado_vencimento
        try:
            venc_naive = venc.replace(tzinfo=None) if venc.tzinfo else venc
        except AttributeError:
            venc_naive = venc
        dias = (venc_naive - agora).days
        if dias <= 30:
            sev = "erro" if dias <= 7 else "warn"
            if dias < 0:
                label = f"Certificado digital VENCIDO há {abs(dias)} dia{'s' if abs(dias) != 1 else ''}"
            else:
                label = f"Certificado digital vence em {dias} dia{'s' if dias != 1 else ''}"
            alertas.append({
                "tipo": "cert_vencendo",
                "severidade": sev,
                "count": None,
                "label": label,
            })

    return {
        "empresa_id": empresa_id,
        "total": len(alertas),
        "itens": alertas,
    }
