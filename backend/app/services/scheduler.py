"""Scheduler in-process (APScheduler) — Central de Documentos v3.

Job diário `enviar_contador_agendado`: às 09:00 UTC (~06:00 BRT) varre
empresas com `dia_envio_contador == today.day` e `envio_automatico_contador`
ligado. Chamada via `enviar_contador_cron()` do serviço.

Ligado só se `settings.envio_contador_cron_ativo` (default False em dev).

**1 worker por container** — no VPS hoje o docker compose sobe 1 uvicorn
por serviço. Se um dia rodar múltiplos workers, adicionar lock por
`EnvioContadorLog.periodo_ref` UNIQUE (a idempotência já protege — vai
falhar o 2º INSERT).
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.models.database import engine
from sqlmodel import Session

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job_enviar_contador() -> None:
    """Wrapper síncrono chamado pelo APScheduler — abre sessão + roda coroutine."""
    from app.services.envio_contador import enviar_contador_cron  # import lazy

    with Session(engine) as session:
        try:
            resultado = asyncio.run(enviar_contador_cron(session))
            logger.info("cron envio_contador: %d empresas processadas · %s", len(resultado), resultado)
        except Exception:  # noqa: BLE001
            logger.exception("cron envio_contador falhou")


def iniciar_scheduler() -> None:
    """Chama uma vez no startup do FastAPI. Idempotente."""
    global _scheduler
    if _scheduler is not None:
        return
    if not settings.envio_contador_cron_ativo:
        logger.info("cron envio_contador desligado (ENVIO_CONTADOR_CRON_ATIVO=false)")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    # 09:00 UTC ≈ 06:00 BRT — batch matinal antes do horário comercial.
    _scheduler.add_job(
        _job_enviar_contador,
        trigger=CronTrigger(hour=9, minute=0),
        id="envio_contador_diario",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("cron envio_contador iniciado — dispara diariamente 09:00 UTC")


def parar_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
