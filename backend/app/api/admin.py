"""Rotas master/admin — gerencia TODAS empresas de todos usuários.

Bootstrap manual (rodar UMA vez no MySQL):
    UPDATE usuarios SET is_admin = 1 WHERE email = 'seu@email.com';

Todas as rotas exigem `Depends(get_current_admin)` — HTTP 403 se o user
não tiver `is_admin=True`.

Escopo desta iteração:
  - Listar/bloquear/deletar (soft) empresas
  - Restaurar empresa soft-deletada
  - Métricas globais

FORA de escopo (deixar pra próxima):
  - Gerenciar usuários
  - Ver notas de outros donos
  - Log de auditoria
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.auth import get_current_admin
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.nota import Nota
from app.models.usuario import Usuario

router = APIRouter(prefix="/admin", tags=["Admin (Master)"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DonoResponse(BaseModel):
    id: int
    nome: str
    email: str


class EmpresaAdminResponse(BaseModel):
    id: int
    cnpj: str
    razao_social: str
    nome_fantasia: Optional[str] = None
    uf: Optional[str] = None
    dono: DonoResponse
    bloqueada: bool
    deletada_em: Optional[datetime] = None
    criado_em: datetime
    total_notas_mes: int = 0
    valor_total_mes: float = 0.0


class BloquearBody(BaseModel):
    bloqueada: bool


class NotasMesBreakdown(BaseModel):
    nfe: int = 0
    nfce: int = 0
    devolucao: int = 0


class TopEmpresa(BaseModel):
    empresa_id: int
    razao_social: str
    cnpj: str
    total_notas: int


class MetricasResponse(BaseModel):
    empresas_total: int
    empresas_ativas: int
    empresas_bloqueadas: int
    empresas_deletadas: int
    usuarios_total: int
    notas_mes: NotasMesBreakdown
    valor_total_mes: float
    top_5_empresas_por_notas: List[TopEmpresa]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inicio_do_mes(agora: Optional[datetime] = None) -> datetime:
    agora = agora or datetime.utcnow()
    return datetime(agora.year, agora.month, 1)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.get("/empresas", response_model=List[EmpresaAdminResponse])
def listar_empresas_admin(
    incluir_deletadas: bool = False,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Lista TODAS empresas do sistema (ignora usuario_id).

    - `incluir_deletadas=false` (default): esconde soft-deletadas.
    - `incluir_deletadas=true`: retorna tudo, inclusive lixeira.

    Cada empresa vem com:
      - `dono`: id/nome/email do usuário responsável
      - `total_notas_mes`: COUNT de notas do mês corrente (qualquer status ≠ rascunho)
      - `valor_total_mes`: SUM de valor_total do mês corrente
    """
    query = select(Empresa)
    if not incluir_deletadas:
        query = query.where(Empresa.deletada_em.is_(None))

    empresas = session.exec(query).all()
    if not empresas:
        return []

    # Buscar donos de uma vez
    dono_ids = {e.usuario_id for e in empresas}
    donos = session.exec(select(Usuario).where(Usuario.id.in_(dono_ids))).all()
    dono_map = {u.id: u for u in donos}

    # Agregar notas do mês por empresa (ignora rascunhos — não são fiscais)
    mes_inicio = _inicio_do_mes()
    empresa_ids = [e.id for e in empresas]
    if empresa_ids:
        agregado = session.exec(
            select(
                Nota.empresa_id,
                func.count(Nota.id).label("total"),
                func.coalesce(func.sum(Nota.valor_total), 0.0).label("valor"),
            )
            .where(
                Nota.empresa_id.in_(empresa_ids),
                Nota.criado_em >= mes_inicio,
                Nota.status != "rascunho",
            )
            .group_by(Nota.empresa_id)
        ).all()
    else:
        agregado = []

    agg_map = {row[0]: (row[1], float(row[2] or 0.0)) for row in agregado}

    resposta: List[EmpresaAdminResponse] = []
    for emp in empresas:
        dono = dono_map.get(emp.usuario_id)
        if not dono:
            # Empresa órfã (dono foi hard-deletado) — pula pra não quebrar response
            continue
        total, valor = agg_map.get(emp.id, (0, 0.0))
        resposta.append(EmpresaAdminResponse(
            id=emp.id,
            cnpj=emp.cnpj,
            razao_social=emp.razao_social,
            nome_fantasia=emp.nome_fantasia,
            uf=emp.uf,
            dono=DonoResponse(id=dono.id, nome=dono.nome, email=dono.email),
            bloqueada=emp.bloqueada,
            deletada_em=emp.deletada_em,
            criado_em=emp.criado_em,
            total_notas_mes=total,
            valor_total_mes=valor,
        ))
    return resposta


@router.patch("/empresas/{empresa_id}/bloquear")
def bloquear_empresa(
    empresa_id: int,
    body: BloquearBody,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Flip do flag `bloqueada`. Não afeta histórico fiscal — apenas trava
    novas emissões (`/emitir`, `/receber-venda`, etc.)."""
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    empresa.bloqueada = body.bloqueada
    session.add(empresa)
    session.commit()
    return {"ok": True, "empresa_id": empresa_id, "bloqueada": empresa.bloqueada}


@router.delete("/empresas/{empresa_id}")
def deletar_empresa_admin(
    empresa_id: int,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Soft-delete idempotente. Não apaga notas (obrigação fiscal 5 anos).
    Empresa some da listagem do dono; ainda visível em
    `GET /admin/empresas?incluir_deletadas=true`."""
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    if empresa.deletada_em is None:
        empresa.deletada_em = datetime.utcnow()
        session.add(empresa)
        session.commit()
    return {"ok": True, "empresa_id": empresa_id, "deletada_em": empresa.deletada_em}


@router.post("/empresas/{empresa_id}/restaurar")
def restaurar_empresa(
    empresa_id: int,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Desfaz soft-delete. Empresa volta a aparecer na listagem do dono."""
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    empresa.deletada_em = None
    session.add(empresa)
    session.commit()
    return {"ok": True, "empresa_id": empresa_id}


@router.get("/metricas", response_model=MetricasResponse)
def metricas_globais(
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Cards de dashboard admin: contadores de empresas, notas do mês por
    modelo, valor total do mês, top 5 empresas por volume."""
    empresas = session.exec(select(Empresa)).all()
    empresas_total = len(empresas)
    empresas_ativas = sum(1 for e in empresas if not e.bloqueada and e.deletada_em is None)
    empresas_bloqueadas = sum(1 for e in empresas if e.bloqueada and e.deletada_em is None)
    empresas_deletadas = sum(1 for e in empresas if e.deletada_em is not None)

    usuarios_total = session.exec(select(func.count(Usuario.id))).one()

    mes_inicio = _inicio_do_mes()

    # Notas do mês agrupadas por modelo e finalidade (para separar devolução)
    notas_mes = session.exec(
        select(Nota).where(
            Nota.criado_em >= mes_inicio,
            Nota.status != "rascunho",
        )
    ).all()

    breakdown = NotasMesBreakdown()
    valor_total_mes = 0.0
    for n in notas_mes:
        valor_total_mes += float(n.valor_total or 0.0)
        if n.finalidade == 4:
            breakdown.devolucao += 1
        elif n.modelo == "55":
            breakdown.nfe += 1
        elif n.modelo == "65":
            breakdown.nfce += 1

    # Top 5 empresas por notas do mês
    top = session.exec(
        select(
            Nota.empresa_id,
            func.count(Nota.id).label("total"),
        )
        .where(
            Nota.criado_em >= mes_inicio,
            Nota.status != "rascunho",
            Nota.empresa_id.is_not(None),
        )
        .group_by(Nota.empresa_id)
        .order_by(func.count(Nota.id).desc())
        .limit(5)
    ).all()

    top_5: List[TopEmpresa] = []
    if top:
        emp_map = {e.id: e for e in empresas}
        for row in top:
            emp_id, total = row[0], row[1]
            emp = emp_map.get(emp_id)
            if not emp:
                continue
            top_5.append(TopEmpresa(
                empresa_id=emp_id,
                razao_social=emp.razao_social,
                cnpj=emp.cnpj,
                total_notas=total,
            ))

    return MetricasResponse(
        empresas_total=empresas_total,
        empresas_ativas=empresas_ativas,
        empresas_bloqueadas=empresas_bloqueadas,
        empresas_deletadas=empresas_deletadas,
        usuarios_total=int(usuarios_total or 0),
        notas_mes=breakdown,
        valor_total_mes=round(valor_total_mes, 2),
        top_5_empresas_por_notas=top_5,
    )
