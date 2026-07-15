from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from typing import List
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.certificado import Certificado
from app.models.usuario import Usuario
from app.schemas.empresa import EmpresaCreate, EmpresaUpdate, EmpresaResponse, CertificadoResponse
from app.api.auth import get_current_user
from app.core.crypto import encrypt_data
from app.services.certificado_service import save_certificado_file, get_certificado_validade

router = APIRouter(prefix="/empresas", tags=["Empresas"])

def format_empresa_response(empresa: Empresa, certificado: Certificado = None) -> EmpresaResponse:
    return EmpresaResponse(
        **empresa.dict(),
        has_csc_token=bool(empresa.csc_token),
        certificado=CertificadoResponse(
            id=certificado.id,
            validade=certificado.validade,
            criado_em=certificado.criado_em
        ) if certificado else None
    )

@router.get("/", response_model=List[EmpresaResponse])
def listar_empresas(session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresas = session.exec(select(Empresa).where(Empresa.usuario_id == current_user.id)).all()
    resultado = []
    for emp in empresas:
        cert = session.exec(select(Certificado).where(Certificado.empresa_id == emp.id)).first()
        resultado.append(format_empresa_response(emp, cert))
    return resultado

@router.post("/", response_model=EmpresaResponse)
def criar_empresa(emp_in: EmpresaCreate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    nova_empresa = Empresa(**emp_in.dict(exclude={"csc_token"}))
    nova_empresa.usuario_id = current_user.id
    if emp_in.csc_token:
        nova_empresa.csc_token = encrypt_data(emp_in.csc_token)
        
    session.add(nova_empresa)
    session.commit()
    session.refresh(nova_empresa)
    return format_empresa_response(nova_empresa)

@router.put("/{empresa_id}", response_model=EmpresaResponse)
def atualizar_empresa(empresa_id: int, emp_in: EmpresaUpdate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        
    emp_data = emp_in.dict(exclude_unset=True)
    if "csc_token" in emp_data and emp_data["csc_token"]:
        emp_data["csc_token"] = encrypt_data(emp_data["csc_token"])
        
    for key, value in emp_data.items():
        setattr(empresa, key, value)
        
    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    
    cert = session.exec(select(Certificado).where(Certificado.empresa_id == empresa.id)).first()
    return format_empresa_response(empresa, cert)

@router.delete("/{empresa_id}")
def deletar_empresa(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    session.delete(empresa)
    session.commit()
    return {"ok": True}

@router.post("/{empresa_id}/certificado", response_model=CertificadoResponse)
def upload_certificado(
    empresa_id: int,
    file: UploadFile = File(...),
    senha: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        
    # Salvar arquivo fisicamente
    file_path = save_certificado_file(empresa.id, file)
    
    # Validar senha e ler validade
    validade = get_certificado_validade(file_path, senha)
    
    # Criptografar senha para salvar no banco
    senha_criptografada = encrypt_data(senha)
    
    # Verificar se já existe certificado para atualizar, senão cria um novo
    cert = session.exec(select(Certificado).where(Certificado.empresa_id == empresa.id)).first()
    if not cert:
        cert = Certificado(empresa_id=empresa.id)
        
    cert.arquivo_path = file_path
    cert.senha_criptografada = senha_criptografada
    cert.validade = validade
    
    session.add(cert)
    session.commit()
    session.refresh(cert)
    
    return CertificadoResponse(id=cert.id, validade=cert.validade, criado_em=cert.criado_em)
