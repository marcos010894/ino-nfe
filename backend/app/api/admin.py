"""Rotas master/admin — gerencia TODAS empresas de todos usuários.

Bootstrap manual (rodar UMA vez no MySQL):
    UPDATE usuarios SET is_admin = 1 WHERE email = 'seu@email.com';

Todas as rotas exigem `Depends(get_current_admin)` — HTTP 403 se o user
não tiver `is_admin=True`.

Escopo desta iteração:
  - Listar/bloquear/deletar (soft) empresas
  - Restaurar empresa soft-deletada
  - Métricas globais
  - Criar/editar/detalhar empresa + Usuario dono (email/senha/token)

FORA de escopo (deixar pra próxima):
  - Gerenciar usuários avulsos (sem empresa)
  - Ver notas de outros donos
  - Log de auditoria
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.auth import get_current_admin
from app.core.crypto import encrypt_data
from app.core.security import create_access_token, get_password_hash
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.nota import Nota
from app.models.regra_fiscal import RegraFiscal
from app.models.usuario import Usuario
from app.services.acbr_api import ACBrAPIService

# Impersonation admin → dono via mesmo mecanismo do SSO (JWT curto).
# 15min é o suficiente pra o admin abrir a empresa e fazer o que precisa,
# sem manter uma "sessão sombra" ativa por muito tempo.
IMPERSONATE_JWT_TTL_MIN = 15

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
    cep: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    dono: DonoResponse
    bloqueada: bool
    deletada_em: Optional[datetime] = None
    criado_em: datetime
    total_notas_mes: int = 0
    valor_total_mes: float = 0.0
    # Cert/ACBr — usado pelo painel admin pra banners e filtros
    certificado_vencimento: Optional[datetime] = None
    tem_certificado: bool = False
    acbr_sincronizado: bool = False
    acbr_ultimo_status: Optional[str] = None


class DonoDetalheResponse(DonoResponse):
    """Dono com token de integração — só o admin recebe esse payload."""
    token_integracao: Optional[str] = None
    ativo: bool = True


class EmpresaAdminDetalheResponse(EmpresaAdminResponse):
    """Detalhe completo da empresa pro painel de gerenciar (admin only).

    Devolve todo o cadastro fiscal + o dono com token de integração pra UI
    conseguir preencher o form de edição sem chamada extra."""
    inscricao_estadual: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    codigo_municipio: Optional[str] = None
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    regime_tributario: str = "Simples Nacional"
    csc_id: Optional[str] = None
    serie_nfe: int = 1
    serie_nfce: int = 1
    proximo_nnf_inicial_nfe: Optional[int] = None
    proximo_nnf_inicial_nfce: Optional[int] = None
    codigo_cliente_innosystem: Optional[str] = None
    dono: DonoDetalheResponse
    certificado_emissor: Optional[str] = None
    certificado_sujeito: Optional[str] = None


class EmpresaAdminCreate(BaseModel):
    """Payload de POST /admin/empresas — cria empresa + Usuario dono.

    Se `dono_email` já existe no banco, associa a empresa ao Usuario existente
    (sem trocar a senha). Senão cria Usuario novo com email/senha/nome.
    """
    # Empresa
    razao_social: str
    nome_fantasia: str
    cnpj: str
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    codigo_municipio: Optional[str] = None
    uf: Optional[str] = None
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    regime_tributario: str = "Simples Nacional"
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None
    serie_nfe: int = 1
    serie_nfce: int = 1
    proximo_nnf_inicial_nfe: Optional[int] = None
    proximo_nnf_inicial_nfce: Optional[int] = None
    codigo_cliente_innosystem: Optional[str] = None
    bloqueada: bool = False
    # Dono (acesso do cliente)
    dono_email: EmailStr
    dono_senha: Optional[str] = None  # obrigatória se dono_email for novo
    dono_nome: Optional[str] = None  # fallback: usa nome_fantasia


class EmpresaAdminUpdate(BaseModel):
    """Payload de PUT /admin/empresas/{id} — atualiza empresa + opcionalmente
    os campos do Usuario dono. Todos os campos são opcionais (patch)."""
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    codigo_municipio: Optional[str] = None
    uf: Optional[str] = None
    contato_telefone: Optional[str] = None
    contato_email: Optional[str] = None
    regime_tributario: Optional[str] = None
    csc_id: Optional[str] = None
    csc_token: Optional[str] = None
    serie_nfe: Optional[int] = None
    serie_nfce: Optional[int] = None
    proximo_nnf_inicial_nfe: Optional[int] = None
    proximo_nnf_inicial_nfce: Optional[int] = None
    codigo_cliente_innosystem: Optional[str] = None
    bloqueada: Optional[bool] = None
    # Dono — só atualiza se vier
    dono_email: Optional[EmailStr] = None
    dono_nome: Optional[str] = None
    dono_senha: Optional[str] = None  # se preenchida, troca a senha


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
    # Timezone-aware UTC — SQLModel/SQLAlchemy recentes recusam datetime naive
    # em comparações (ValueError: "Datetime values must have timezone information").
    agora = agora or datetime.now(timezone.utc)
    return datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)


def _garantir_token_integracao(usuario: Usuario, session: Session) -> None:
    """Gera token_integracao lazy — mesmo pattern de /auth/me. Idempotente."""
    if not usuario.token_integracao:
        usuario.token_integracao = secrets.token_urlsafe(32)
        session.add(usuario)


def _montar_detalhe(empresa: Empresa, dono: Usuario) -> EmpresaAdminDetalheResponse:
    """Serializa empresa + dono com token pro admin — evita duplicar
    a lista de campos em POST/PUT/GET."""
    return EmpresaAdminDetalheResponse(
        id=empresa.id,
        cnpj=empresa.cnpj,
        razao_social=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        inscricao_estadual=empresa.inscricao_estadual,
        cep=empresa.cep,
        logradouro=empresa.logradouro,
        numero=empresa.numero,
        bairro=empresa.bairro,
        cidade=empresa.cidade,
        codigo_municipio=empresa.codigo_municipio,
        uf=empresa.uf,
        contato_telefone=empresa.contato_telefone,
        contato_email=empresa.contato_email,
        regime_tributario=empresa.regime_tributario,
        csc_id=empresa.csc_id,
        serie_nfe=empresa.serie_nfe,
        serie_nfce=empresa.serie_nfce,
        proximo_nnf_inicial_nfe=empresa.proximo_nnf_inicial_nfe,
        proximo_nnf_inicial_nfce=empresa.proximo_nnf_inicial_nfce,
        codigo_cliente_innosystem=empresa.codigo_cliente_innosystem,
        bloqueada=empresa.bloqueada,
        deletada_em=empresa.deletada_em,
        criado_em=empresa.criado_em,
        total_notas_mes=0,
        valor_total_mes=0.0,
        certificado_vencimento=empresa.certificado_vencimento,
        certificado_emissor=empresa.certificado_emissor,
        certificado_sujeito=empresa.certificado_sujeito,
        tem_certificado=bool(empresa.certificado_base64),
        acbr_sincronizado=empresa.acbr_sincronizado,
        acbr_ultimo_status=empresa.acbr_ultimo_status,
        dono=DonoDetalheResponse(
            id=dono.id,
            nome=dono.nome,
            email=dono.email,
            token_integracao=dono.token_integracao,
            ativo=dono.ativo,
        ),
    )


def _criar_regra_fiscal_padrao_local(empresa_id: int, session: Session) -> None:
    """Mesma regra default de empresas.py — inline pra não criar dep circular
    ao importar do módulo /empresas."""
    existe = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)).first()
    if existe:
        return
    session.add(RegraFiscal(
        empresa_id=empresa_id,
        nome="Regra Fiscal Padrão (Simples Nacional — pós-Reforma 2026)",
        cfop="5102",
        ncm_padrao="61091000",
        origem_icms="0",
        cst_csosn="102",
        icms_aliquota=0.0,
        pis_cst="07",
        pis_aliquota=0.0,
        cofins_cst="07",
        cofins_aliquota=0.0,
        cbs_cst="000",
        cbs_cclass_trib="000001",  # 000000 dá cStat 1023; 000001 é o default padrão SN
        cbs_aliquota=0.9,
        ibs_uf_aliquota=0.1,
        ibs_mun_aliquota=0.0,
        regime_monofasico=False,
        credito_presumido=False,
        diferimento=False,
        padrao=True,
        criado_em=datetime.utcnow(),
    ))
    session.commit()


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
            cep=emp.cep,
            cidade=emp.cidade,
            uf=emp.uf,
            dono=DonoResponse(id=dono.id, nome=dono.nome, email=dono.email),
            bloqueada=emp.bloqueada,
            deletada_em=emp.deletada_em,
            criado_em=emp.criado_em,
            total_notas_mes=total,
            valor_total_mes=valor,
            certificado_vencimento=emp.certificado_vencimento,
            tem_certificado=bool(emp.certificado_base64),
            acbr_sincronizado=emp.acbr_sincronizado,
            acbr_ultimo_status=emp.acbr_ultimo_status,
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


@router.get("/empresas/{empresa_id}", response_model=EmpresaAdminDetalheResponse)
def detalhe_empresa_admin(
    empresa_id: int,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Retorna a empresa completa + Usuario dono (com token_integracao).

    Endpoint dedicado pra tela de gerenciar do master — a versão normal
    /empresas/ não devolve `token_integracao` de outros donos."""
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    dono = session.get(Usuario, empresa.usuario_id)
    if not dono:
        raise HTTPException(status_code=500, detail="Dono da empresa não existe (banco inconsistente).")
    _garantir_token_integracao(dono, session)
    session.commit()
    session.refresh(dono)
    return _montar_detalhe(empresa, dono)


@router.post("/empresas", response_model=EmpresaAdminDetalheResponse)
async def criar_empresa_admin(
    payload: EmpresaAdminCreate,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Cria empresa + Usuario dono (acesso do cliente).

    Regras:
    - Se `dono_email` já existe: associa empresa ao Usuario existente,
      ignora `dono_senha`/`dono_nome` (não sobrescreve conta ativa).
    - Se `dono_email` é novo: exige `dono_senha`; usa `dono_nome` ou
      cai em `nome_fantasia`.
    - CNPJ único: 400 se já existir empresa (mesmo soft-deletada).
    - Sincroniza empresa + certificado (se subir cert depois) com a ACBr;
      falha reportada em `acbr_ultimo_status` sem bloquear o cadastro.
    """
    # CNPJ duplicado — evita empresa fantasma
    cnpj_limpo = payload.cnpj
    empresa_existente = session.exec(select(Empresa).where(Empresa.cnpj == cnpj_limpo)).first()
    if empresa_existente:
        raise HTTPException(status_code=400, detail=f"CNPJ {cnpj_limpo} já cadastrado (empresa #{empresa_existente.id}).")

    # Resolve/cria Usuario dono
    dono = session.exec(select(Usuario).where(Usuario.email == payload.dono_email)).first()
    if dono is None:
        if not payload.dono_senha or len(payload.dono_senha) < 6:
            raise HTTPException(status_code=400, detail="Senha do dono é obrigatória (mín. 6 caracteres) quando o e-mail não existe ainda.")
        dono = Usuario(
            nome=(payload.dono_nome or payload.nome_fantasia or payload.razao_social)[:100],
            email=payload.dono_email,
            senha_hash=get_password_hash(payload.dono_senha),
            ativo=True,
        )
        session.add(dono)
        session.commit()
        session.refresh(dono)
    _garantir_token_integracao(dono, session)
    session.commit()
    session.refresh(dono)

    # Cria empresa
    empresa = Empresa(
        usuario_id=dono.id,
        razao_social=payload.razao_social,
        nome_fantasia=payload.nome_fantasia,
        cnpj=cnpj_limpo,
        inscricao_estadual=payload.inscricao_estadual,
        cep=payload.cep,
        logradouro=payload.logradouro,
        numero=payload.numero,
        bairro=payload.bairro,
        cidade=payload.cidade,
        codigo_municipio=payload.codigo_municipio,
        uf=payload.uf,
        contato_telefone=payload.contato_telefone,
        contato_email=payload.contato_email,
        regime_tributario=payload.regime_tributario,
        csc_id=payload.csc_id,
        csc_token=encrypt_data(payload.csc_token) if payload.csc_token else None,
        serie_nfe=payload.serie_nfe or 1,
        serie_nfce=payload.serie_nfce or 1,
        proximo_nnf_inicial_nfe=payload.proximo_nnf_inicial_nfe,
        proximo_nnf_inicial_nfce=payload.proximo_nnf_inicial_nfce,
        codigo_cliente_innosystem=payload.codigo_cliente_innosystem,
        bloqueada=payload.bloqueada,
    )
    session.add(empresa)
    session.commit()
    session.refresh(empresa)

    _criar_regra_fiscal_padrao_local(empresa.id, session)

    # Sincroniza cadastral com ACBr — falha vira status, não bloqueia.
    acbr = ACBrAPIService()
    ok, res = await acbr.sincronizar_empresa_acbr(empresa)
    empresa.acbr_sincronizado = ok
    empresa.acbr_ultimo_status = (
        res.get("motivo") or res.get("status") or "Sincronizado"
        if ok else f"Erro sync: {res.get('erro') or res.get('status_code') or res}"
    )
    session.add(empresa)
    session.commit()
    session.refresh(empresa)

    return _montar_detalhe(empresa, dono)


@router.put("/empresas/{empresa_id}", response_model=EmpresaAdminDetalheResponse)
async def atualizar_empresa_admin(
    empresa_id: int,
    payload: EmpresaAdminUpdate,
    session: Session = Depends(get_session),
    _admin: Usuario = Depends(get_current_admin),
):
    """Atualiza empresa + opcionalmente os dados do Usuario dono.

    - Campos vazios são ignorados (patch).
    - `dono_email`: se preenchido e diferente do atual, reatribui a empresa
      a esse email (cria Usuario novo se não existir E `dono_senha` vier).
    - `dono_senha`: troca a senha do dono atual (ou do novo).
    - Sincronização ACBr é rodada no fim (mesmo pattern do PUT /empresas/).
    """
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    dono = session.get(Usuario, empresa.usuario_id)
    if not dono:
        raise HTTPException(status_code=500, detail="Dono da empresa não existe (banco inconsistente).")

    # Reatribuição de dono (troca de email)
    if payload.dono_email and payload.dono_email != dono.email:
        outro = session.exec(select(Usuario).where(Usuario.email == payload.dono_email)).first()
        if outro is None:
            if not payload.dono_senha or len(payload.dono_senha) < 6:
                raise HTTPException(status_code=400, detail="Senha é obrigatória (mín. 6) quando o novo e-mail ainda não existe.")
            outro = Usuario(
                nome=(payload.dono_nome or empresa.nome_fantasia or empresa.razao_social)[:100],
                email=payload.dono_email,
                senha_hash=get_password_hash(payload.dono_senha),
                ativo=True,
            )
            session.add(outro)
            session.commit()
            session.refresh(outro)
        _garantir_token_integracao(outro, session)
        session.commit()
        session.refresh(outro)
        empresa.usuario_id = outro.id
        dono = outro

    # Atualiza dono atual
    if payload.dono_nome:
        dono.nome = payload.dono_nome
    if payload.dono_senha and len(payload.dono_senha) >= 6:
        dono.senha_hash = get_password_hash(payload.dono_senha)
    session.add(dono)

    # Atualiza empresa (patch)
    campos_empresa = payload.dict(
        exclude_unset=True,
        exclude={"dono_email", "dono_nome", "dono_senha"},
    )
    if "csc_token" in campos_empresa and campos_empresa["csc_token"]:
        campos_empresa["csc_token"] = encrypt_data(campos_empresa["csc_token"])
    elif "csc_token" in campos_empresa and not campos_empresa["csc_token"]:
        # string vazia = "não alterar" (mesmo pattern do form legado)
        del campos_empresa["csc_token"]
    for k, v in campos_empresa.items():
        setattr(empresa, k, v)

    # Sincroniza cadastral com ACBr
    acbr = ACBrAPIService()
    ok, res = await acbr.sincronizar_empresa_acbr(empresa)
    empresa.acbr_sincronizado = ok
    empresa.acbr_ultimo_status = (
        res.get("motivo") or res.get("status") or "Sincronizado"
        if ok else f"Erro sync: {res.get('erro') or res.get('status_code') or res}"
    )

    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    session.refresh(dono)

    return _montar_detalhe(empresa, dono)


class ImpersonateResponse(BaseModel):
    """Payload devolvido pro admin abrir a empresa como se fosse o dono."""
    sso_url: str  # /sso?token=<jwt>&redirect=/emitir&empresa_id=<id>
    dono_email: str
    empresa_id: int
    expires_in: int  # segundos


@router.post("/empresas/{empresa_id}/impersonate", response_model=ImpersonateResponse)
def impersonate_dono(
    empresa_id: int,
    session: Session = Depends(get_session),
    admin: Usuario = Depends(get_current_admin),
):
    """Devolve uma URL SSO pro admin abrir a empresa como se fosse o dono.

    Fluxo: master clica em "Acessar emissor" → frontend chama esta rota →
    recebe `sso_url` com JWT curto do dono → abre em nova aba. A nova aba
    passa por `/sso?token=...` que grava a sessão e navega pro `/emitir`
    já filtrado pela empresa (via `empresa_id=<id>` na query).

    JWT tem TTL de 15min e claim `origin=admin_impersonate` +
    `impersonated_by=<admin.email>` pra auditoria (aparece em log de acesso
    e no payload do próprio token — não é escondido do usuário).
    """
    empresa = session.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    dono = session.get(Usuario, empresa.usuario_id)
    if not dono:
        raise HTTPException(status_code=500, detail="Dono da empresa não existe (banco inconsistente).")

    ttl = timedelta(minutes=IMPERSONATE_JWT_TTL_MIN)
    token = create_access_token(
        data={
            "sub": dono.email,
            "origin": "admin_impersonate",
            "impersonated_by": admin.email,
        },
        expires_delta=ttl,
    )
    # A tela SSO faz replace da URL (token some do histórico); o empresa_id
    # segue como query pra o /emitir abrir na empresa certa.
    sso_url = f"/sso?token={token}&redirect=/emitir&empresa_id={empresa.id}"

    return ImpersonateResponse(
        sso_url=sso_url,
        dono_email=dono.email,
        empresa_id=empresa.id,
        expires_in=int(ttl.total_seconds()),
    )


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
