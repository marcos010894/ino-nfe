"""Envio de XMLs pro contador — Central de Documentos v3.

Duas entradas:
1. Manual: `POST /empresas/{id}/contador/enviar` (dono aperta botão).
2. Cron: `app.services.scheduler.enviar_contador_agendado` (dia N do mês).

Fluxo comum:
1. Valida config (email do contador presente + SMTP configurado).
2. Carrega notas do período (do 1º dia do mês até `fim`).
3. Reusa `exportador_notas.preparar_lote` — mesmo ZIP que o download.
4. Envia via `email_service.enviar_email` com ZIP anexado.
5. Grava `EnvioContadorLog` (ok/erro + idempotência do cron).

Regras:
- V3.7: cron só envia se `fim` estiver em mês fechado (mês anterior ao atual).
  Envio manual permite qualquer período (dono pode adiantar).
- Cron ignora empresa que já tem log ok=True pro periodo_ref.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.models.empresa import Empresa
from app.models.envio_contador_log import EnvioContadorLog
from app.models.nota import Nota
from app.services.email_service import (
    ASSUNTO_PADRAO,
    MENSAGEM_PADRAO,
    EmailAttachment,
    aplicar_template,
    enviar_email,
)
from app.services.exportador_notas import formatar_periodo_mensal, preparar_lote


class ContadorNaoConfiguradoError(RuntimeError):
    """Faltam nome_contador / email_contador na empresa."""


class SmtpNaoConfiguradoError(RuntimeError):
    """Faltam envs SMTP_* — bloqueia envio real."""


class SemNotasNoPeriodoError(RuntimeError):
    """Período selecionado tem 0 notas autorizadas/canceladas — nada a enviar."""


@dataclass
class ResultadoEnvio:
    ok: bool
    periodo_ref: str  # "YYYY-MM"
    destinatarios: list[str]
    qtd_notas: int
    erro: Optional[str] = None


def _garantir_smtp() -> None:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise SmtpNaoConfiguradoError(
            "SMTP não configurado — defina SMTP_HOST, SMTP_USER, SMTP_PASSWORD no VPS."
        )


def _garantir_contador(empresa: Empresa) -> None:
    if not (empresa.nome_contador and empresa.email_contador):
        raise ContadorNaoConfiguradoError(
            "Empresa sem dados do contador — configure na engrenagem antes de enviar."
        )


def periodo_mes_atual_ate_agora() -> tuple[datetime, datetime]:
    """(1º dia do mês 00:00, agora)."""
    now = datetime.utcnow()
    inicio = datetime(now.year, now.month, 1, 0, 0, 0)
    return inicio, now


def periodo_mes_anterior_completo() -> tuple[datetime, datetime]:
    """(1º dia do mês passado, último dia 23:59:59). Base do cron mensal."""
    now = datetime.utcnow()
    if now.month == 1:
        ano, mes = now.year - 1, 12
    else:
        ano, mes = now.year, now.month - 1
    inicio = datetime(ano, mes, 1, 0, 0, 0)
    ultimo_dia = monthrange(ano, mes)[1]
    fim = datetime(ano, mes, ultimo_dia, 23, 59, 59)
    return inicio, fim


def _periodo_ref(inicio: datetime) -> str:
    return f"{inicio.year:04d}-{inicio.month:02d}"


def _ja_enviou_periodo(session: Session, empresa_id: int, periodo_ref: str) -> bool:
    row = session.exec(
        select(EnvioContadorLog).where(
            EnvioContadorLog.empresa_id == empresa_id,
            EnvioContadorLog.periodo_ref == periodo_ref,
            EnvioContadorLog.ok == True,  # noqa: E712
        )
    ).first()
    return row is not None


def _carregar_notas_periodo(
    session: Session, empresa_id: int, inicio: datetime, fim: datetime
) -> list[Nota]:
    """Só notas com documento fiscal — autorizada/cancelada."""
    notas = session.exec(
        select(Nota).where(
            Nota.empresa_id == empresa_id,
            Nota.status.in_(["autorizada", "cancelada"]),  # type: ignore[attr-defined]
        )
    ).all()
    return [n for n in notas if n.criado_em and inicio <= n.criado_em <= fim]


async def enviar_para_contador(
    *,
    session: Session,
    empresa: Empresa,
    inicio: datetime,
    fim: datetime,
    disparado_por: str,  # "manual" | "cron"
    assunto_override: Optional[str] = None,   # override do envio manual
    mensagem_override: Optional[str] = None,  # override do envio manual
) -> ResultadoEnvio:
    """Envio síncrono (do ponto de vista do endpoint). Grava log sempre.

    Levanta ContadorNaoConfiguradoError / SmtpNaoConfiguradoError antes de
    tocar em qualquer coisa, e SemNotasNoPeriodoError se o filtro pegar 0
    documentos válidos. Se der ruim depois disso, grava `ok=False` e re-levanta.
    """
    _garantir_contador(empresa)
    _garantir_smtp()

    periodo_ref = _periodo_ref(inicio)
    periodo_label = formatar_periodo_mensal(inicio)
    destinatarios = [empresa.email_contador]
    if empresa.email_cc_contador:
        destinatarios.append(empresa.email_cc_contador)

    notas = _carregar_notas_periodo(session, empresa.id, inicio, fim)
    if not notas:
        # Nada de mandar email vazio — poluiria a caixa do contador e
        # confundiria o dono (viu que "enviou" mas não tinha nota).
        raise SemNotasNoPeriodoError(
            f"Sem notas autorizadas/canceladas em {periodo_label} — nada a enviar."
        )
    lote = await preparar_lote(empresa, notas, inicio, fim, incluir="ambos")

    empresa_label = empresa.nome_fantasia or empresa.razao_social
    # Prioridade: override do envio > template salvo na empresa > default do backend.
    assunto = aplicar_template(
        assunto_override or empresa.assunto_email_contador,
        contador=empresa.nome_contador or "",
        empresa=empresa_label,
        periodo=periodo_label,
        fallback=ASSUNTO_PADRAO,
    )
    corpo = aplicar_template(
        mensagem_override or empresa.mensagem_email_contador,
        contador=empresa.nome_contador or "",
        empresa=empresa_label,
        periodo=periodo_label,
        fallback=MENSAGEM_PADRAO,
    )

    anexo = EmailAttachment(
        filename=lote.filename,
        content=lote.zip_bytes,
        content_type="application/zip",
    )

    log = EnvioContadorLog(
        empresa_id=empresa.id,
        periodo_ref=periodo_ref,
        destinatarios=", ".join(destinatarios),
        qtd_notas=lote.resumo.qtd_total,
        disparado_por=disparado_por,
    )

    try:
        enviar_email(
            to=empresa.email_contador,
            cc=empresa.email_cc_contador,
            subject=assunto,
            body_text=corpo,
            reply_to=empresa.contato_email or None,
            attachments=[anexo],
        )
        log.ok = True
    except Exception as exc:  # noqa: BLE001 — grava tudo, quem chama decide
        log.ok = False
        log.erro = str(exc)[:2000]
        session.add(log)
        session.commit()
        raise
    else:
        session.add(log)
        session.commit()

    return ResultadoEnvio(
        ok=True,
        periodo_ref=periodo_ref,
        destinatarios=destinatarios,
        qtd_notas=lote.resumo.qtd_total,
    )


async def enviar_contador_cron(session: Session) -> list[dict]:
    """Roda o batch diário — só envia pra empresas com dia_envio == today.day.

    V3.7 gate: sempre envia o mês fechado (mês anterior). Se o cliente marcou
    dia 5, no dia 5 do mês vai o consolidado do mês anterior.
    """
    hoje = datetime.utcnow().date()
    empresas = session.exec(
        select(Empresa).where(
            Empresa.envio_automatico_contador == True,  # noqa: E712
            Empresa.dia_envio_contador == hoje.day,
            Empresa.bloqueada == False,  # noqa: E712
            Empresa.deletada_em.is_(None),  # type: ignore[union-attr]
        )
    ).all()

    inicio, fim = periodo_mes_anterior_completo()
    periodo_ref = _periodo_ref(inicio)
    resultado: list[dict] = []

    for empresa in empresas:
        item = {"empresa_id": empresa.id, "cnpj": empresa.cnpj, "ok": False, "erro": None}
        try:
            if _ja_enviou_periodo(session, empresa.id, periodo_ref):
                item["skip"] = "ja_enviado"
                item["ok"] = True
                resultado.append(item)
                continue
            r = await enviar_para_contador(
                session=session,
                empresa=empresa,
                inicio=inicio,
                fim=fim,
                disparado_por="cron",
            )
            item["ok"] = r.ok
            item["qtd_notas"] = r.qtd_notas
        except Exception as exc:  # noqa: BLE001 — 1 empresa quebrar não trava as outras
            item["erro"] = str(exc)[:500]
        resultado.append(item)

    return resultado
