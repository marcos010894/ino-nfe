"""Dashboard per-user — cards + gráficos da tela `Visão Geral`.

Uma única rota `/dashboard/resumo` agrega tudo que a Home precisa numa
chamada só (evita 5 requests do front pra cada card/gráfico).
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.auth import get_current_user
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.nota import Nota
from app.models.usuario import Usuario

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PontoValor(BaseModel):
    name: str
    valor: float


class PontoStatus(BaseModel):
    name: str
    value: int
    color: str


class PontoVolume(BaseModel):
    name: str
    emissao: int
    canceladas: int


class PontoTicket(BaseModel):
    name: str
    ticket: float


class Cards(BaseModel):
    notas_mes: int
    notas_mes_delta_pct: Optional[float] = None  # None = mês anterior sem dados
    volume_mes: float
    volume_mes_delta_pct: Optional[float] = None
    empresas_ativas: int
    rejeicoes_mes: int


class ResumoResponse(BaseModel):
    cards: Cards
    faturamento_diario: List[PontoValor]      # últimos 7 dias
    status_hoje: List[PontoStatus]             # donut
    historico_6meses: List[PontoVolume]        # barras
    ticket_medio_semanas: List[PontoTicket]    # últimas 4 semanas
    escopo: str                                 # "global" (admin) ou "usuario"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
_MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

_STATUS_EMITIDA = {"autorizada", "rejeitada", "cancelada", "processando", "pendente_consulta", "denegada"}


def _inicio_do_dia(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


def _inicio_do_mes(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1)


def _delta_pct(atual: float, anterior: float) -> Optional[float]:
    if anterior <= 0:
        return None
    return round(((atual - anterior) / anterior) * 100, 1)


# ---------------------------------------------------------------------------
# Rota
# ---------------------------------------------------------------------------

@router.get("/resumo", response_model=ResumoResponse)
def dashboard_resumo(
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Cards + gráficos da Home. Admin (is_admin=True) vê agregado global de
    todos os users; dono comum vê só as próprias empresas/notas."""
    is_admin = bool(getattr(current_user, "is_admin", False))
    agora = datetime.utcnow()
    mes_atual_ini = _inicio_do_mes(agora)
    mes_anterior_ini = _inicio_do_mes(mes_atual_ini - timedelta(days=1))
    hoje_ini = _inicio_do_dia(agora)
    sete_dias_atras = hoje_ini - timedelta(days=6)  # inclui hoje = 7 dias
    quatro_semanas_atras = hoje_ini - timedelta(days=27)  # 4 semanas cheias
    # 6 meses cheios (mês atual + 5 anteriores)
    m = mes_atual_ini
    for _ in range(5):
        m = _inicio_do_mes(m - timedelta(days=1))
    janela_6meses = m

    # Puxa numa query só o que cobre a janela mais ampla (6 meses).
    # Admin vê tudo; dono comum filtra por usuario_id. Sempre ignora rascunho.
    notas_query = select(Nota).where(
        Nota.status != "rascunho",
        Nota.criado_em >= janela_6meses,
    )
    if not is_admin:
        notas_query = notas_query.where(Nota.usuario_id == current_user.id)
    notas: List[Nota] = session.exec(notas_query).all()

    # -------- Cards
    notas_mes_atual = [n for n in notas if n.criado_em >= mes_atual_ini]
    notas_mes_anterior = [n for n in notas if mes_anterior_ini <= n.criado_em < mes_atual_ini]

    volume_mes_atual = sum(float(n.valor_total or 0) for n in notas_mes_atual if n.status == "autorizada")
    volume_mes_anterior = sum(float(n.valor_total or 0) for n in notas_mes_anterior if n.status == "autorizada")

    empresas_query = select(Empresa).where(
        Empresa.bloqueada == False,  # noqa: E712 — SQLModel exige ==
        Empresa.deletada_em.is_(None),
    )
    if not is_admin:
        empresas_query = empresas_query.where(Empresa.usuario_id == current_user.id)
    empresas_ativas = session.exec(empresas_query).all()

    rejeicoes_mes = sum(1 for n in notas_mes_atual if n.status == "rejeitada")

    cards = Cards(
        notas_mes=len(notas_mes_atual),
        notas_mes_delta_pct=_delta_pct(len(notas_mes_atual), len(notas_mes_anterior)),
        volume_mes=round(volume_mes_atual, 2),
        volume_mes_delta_pct=_delta_pct(volume_mes_atual, volume_mes_anterior),
        empresas_ativas=len(empresas_ativas),
        rejeicoes_mes=rejeicoes_mes,
    )

    # -------- Faturamento diário (últimos 7 dias, autorizadas)
    fat_por_dia: Dict[datetime, float] = {}
    for i in range(7):
        d = sete_dias_atras + timedelta(days=i)
        fat_por_dia[d] = 0.0
    for n in notas:
        if n.status != "autorizada":
            continue
        d = _inicio_do_dia(n.criado_em)
        if d in fat_por_dia:
            fat_por_dia[d] += float(n.valor_total or 0)
    faturamento_diario = [
        PontoValor(name=_DIAS_PT[d.weekday()], valor=round(v, 2))
        for d, v in sorted(fat_por_dia.items())
    ]

    # -------- Status hoje (donut)
    notas_hoje = [n for n in notas if n.criado_em >= hoje_ini]
    autorizadas_hoje = sum(1 for n in notas_hoje if n.status == "autorizada")
    pendentes_hoje = sum(1 for n in notas_hoje if n.status in ("processando", "pendente_consulta"))
    rejeitadas_hoje = sum(1 for n in notas_hoje if n.status in ("rejeitada", "denegada"))
    status_hoje = [
        PontoStatus(name="Autorizadas", value=autorizadas_hoje, color="#1e874b"),
        PontoStatus(name="Pendentes", value=pendentes_hoje, color="#b7791f"),
        PontoStatus(name="Rejeitadas", value=rejeitadas_hoje, color="#c0392b"),
    ]

    # -------- Histórico 6 meses (barras)
    # Cria buckets pros últimos 6 meses (ordem cronológica)
    buckets: List[datetime] = []
    m = janela_6meses
    while m <= mes_atual_ini:
        buckets.append(m)
        # próximo mês
        if m.month == 12:
            m = datetime(m.year + 1, 1, 1)
        else:
            m = datetime(m.year, m.month + 1, 1)

    hist_map: Dict[datetime, Dict[str, int]] = {b: {"emissao": 0, "canceladas": 0} for b in buckets}
    for n in notas:
        key = _inicio_do_mes(n.criado_em)
        if key not in hist_map:
            continue
        if n.status == "cancelada":
            hist_map[key]["canceladas"] += 1
        elif n.status in ("autorizada", "rejeitada", "denegada"):
            hist_map[key]["emissao"] += 1
    historico_6meses = [
        PontoVolume(
            name=_MESES_PT[b.month - 1],
            emissao=hist_map[b]["emissao"],
            canceladas=hist_map[b]["canceladas"],
        )
        for b in buckets
    ]

    # -------- Ticket médio últimas 4 semanas
    ticket_por_semana: List[PontoTicket] = []
    for i in range(4):
        sem_ini = quatro_semanas_atras + timedelta(days=i * 7)
        sem_fim = sem_ini + timedelta(days=7)
        autorizadas_semana = [
            float(n.valor_total or 0)
            for n in notas
            if n.status == "autorizada" and sem_ini <= n.criado_em < sem_fim
        ]
        avg = round(sum(autorizadas_semana) / len(autorizadas_semana), 2) if autorizadas_semana else 0.0
        ticket_por_semana.append(PontoTicket(name=f"Sem {i + 1}", ticket=avg))

    return ResumoResponse(
        cards=cards,
        faturamento_diario=faturamento_diario,
        status_hoje=status_hoje,
        historico_6meses=historico_6meses,
        ticket_medio_semanas=ticket_por_semana,
        escopo="global" if is_admin else "usuario",
    )
