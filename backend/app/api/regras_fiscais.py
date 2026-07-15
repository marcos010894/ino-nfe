from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.models.usuario import Usuario
from app.schemas.regra_fiscal import RegraFiscalCreate, RegraFiscalUpdate, RegraFiscalResponse
from app.api.auth import get_current_user

router = APIRouter(prefix="/empresas/{empresa_id}/regras", tags=["Regras Fiscais"])

def _verificar_empresa(empresa_id: int, session: Session, current_user: Usuario) -> Empresa:
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return empresa

def _ajustar_regra_padrao(empresa_id: int, regra_id_padrao: int, session: Session):
    """Se uma regra está sendo definida como padrão, remove o padrão das outras."""
    outras_regras = session.exec(
        select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id, RegraFiscal.id != regra_id_padrao)
    ).all()
    for regra in outras_regras:
        if regra.padrao:
            regra.padrao = False
            session.add(regra)

@router.get("/", response_model=List[RegraFiscalResponse])
def listar_regras(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    regras = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)).all()
    return regras

@router.post("/", response_model=RegraFiscalResponse)
def criar_regra(empresa_id: int, regra_in: RegraFiscalCreate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    
    nova_regra = RegraFiscal(**regra_in.dict())
    nova_regra.empresa_id = empresa_id
    
    session.add(nova_regra)
    session.commit()
    session.refresh(nova_regra)
    
    if nova_regra.padrao:
        _ajustar_regra_padrao(empresa_id, nova_regra.id, session)
        session.commit()
        session.refresh(nova_regra)
        
    return nova_regra

@router.put("/{regra_id}", response_model=RegraFiscalResponse)
def atualizar_regra(empresa_id: int, regra_id: int, regra_in: RegraFiscalUpdate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    
    regra = session.get(RegraFiscal, regra_id)
    if not regra or regra.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Regra fiscal não encontrada.")
        
    regra_data = regra_in.dict(exclude_unset=True)
    for key, value in regra_data.items():
        setattr(regra, key, value)
        
    session.add(regra)
    session.commit()
    session.refresh(regra)
    
    if regra.padrao:
        _ajustar_regra_padrao(empresa_id, regra.id, session)
        session.commit()
        session.refresh(regra)
        
    return regra

@router.delete("/{regra_id}")
def deletar_regra(empresa_id: int, regra_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    
    regra = session.get(RegraFiscal, regra_id)
    if not regra or regra.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Regra fiscal não encontrada.")
        
    session.delete(regra)
    session.commit()
    return {"ok": True}
