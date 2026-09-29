"""Log de envio de XMLs pro contador — Central de Documentos v3.

Idempotência do cron: um único registro `ok=True` por (empresa_id, periodo_ref)
impede que o job dispare 2x pro mesmo mês. `disparado_por` distingue "manual"
(botão Enviar ao contador) de "cron" (job automático dia N).
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class EnvioContadorLog(SQLModel, table=True):
    __tablename__ = "envio_contador_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresas.id", index=True)
    # "YYYY-MM" — período de referência (mês) das notas exportadas.
    periodo_ref: str = Field(max_length=7, index=True)
    enviado_em: datetime = Field(default_factory=datetime.utcnow)
    # CSV dos destinatários (contador + cc), pra rastrear pra quem foi.
    destinatarios: Optional[str] = None
    qtd_notas: int = Field(default=0)
    ok: bool = Field(default=True)
    erro: Optional[str] = None
    # "manual" ou "cron" — o cron ignora empresa que já tem `ok=True` no período.
    disparado_por: Optional[str] = None
