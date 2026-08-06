from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from typing import List
from datetime import datetime
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.models.usuario import Usuario
from app.schemas.empresa import EmpresaCreate, EmpresaUpdate, EmpresaResponse, CertificadoResponse
from app.api.auth import get_current_user
from app.core.crypto import encrypt_data, decrypt_data
from app.services.acbr_api import ACBrAPIService

router = APIRouter(prefix="/empresas", tags=["Empresas"])

def format_empresa_response(empresa: Empresa) -> EmpresaResponse:
    return EmpresaResponse(
        **empresa.dict(),
        has_csc_token=bool(empresa.csc_token),
        has_certificado=bool(empresa.certificado_base64)
    )

def _criar_regra_fiscal_padrao(empresa_id: int, session: Session):
    regra_existente = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)).first()
    if not regra_existente:
        nova_regra = RegraFiscal(
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
            # Reforma Tributária — vigente desde 2026-08-01. Alíquotas
            # simbólicas (0.9% CBS na fase de transição). Alíquotas reais
            # devem ser configuradas por cada empresa conforme sua atividade.
            cbs_cst="000",
            cbs_cclass_trib="000000",
            cbs_aliquota=0.9,
            ibs_uf_aliquota=0.0,
            ibs_mun_aliquota=0.0,
            regime_monofasico=False,
            credito_presumido=False,
            diferimento=False,
            padrao=True,
            criado_em=datetime.utcnow()
        )
        session.add(nova_regra)
        session.commit()

@router.get("/acbr/status")
async def testar_conexao_acbr(current_user: Usuario = Depends(get_current_user)):
    """Health-check real da ACBr API (OAuth2 + endpoint autenticado). Sem simulação."""
    acbr = ACBrAPIService()
    ok, res = await acbr.testar_conexao()
    if not ok:
        raise HTTPException(status_code=502, detail=res)
    return res


@router.get("/", response_model=List[EmpresaResponse])
def listar_empresas(session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresas = session.exec(select(Empresa).where(Empresa.usuario_id == current_user.id)).all()
    return [format_empresa_response(emp) for emp in empresas]

@router.post("/", response_model=EmpresaResponse)
async def criar_empresa(emp_in: EmpresaCreate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    nova_empresa = Empresa(**emp_in.dict(exclude={"csc_token"}))
    nova_empresa.usuario_id = current_user.id
    if emp_in.csc_token:
        nova_empresa.csc_token = encrypt_data(emp_in.csc_token)
        
    session.add(nova_empresa)
    session.commit()
    session.refresh(nova_empresa)
    
    # Criar regra fiscal padrão automaticamente
    _criar_regra_fiscal_padrao(nova_empresa.id, session)
    
    # Sincronização inicial com ACBr (falhas de homologação são reportadas — sem simulação silenciosa)
    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.sincronizar_empresa_acbr(nova_empresa)
    nova_empresa.acbr_sincronizado = ok
    if ok:
        nova_empresa.acbr_ultimo_status = res.get("motivo") or res.get("status") or "Sincronizado"
    else:
        nova_empresa.acbr_ultimo_status = f"Erro sync: {res.get('erro') or res.get('status_code') or res}"
    session.add(nova_empresa)
    session.commit()
    session.refresh(nova_empresa)

    return format_empresa_response(nova_empresa)

@router.put("/{empresa_id}", response_model=EmpresaResponse)
async def atualizar_empresa(empresa_id: int, emp_in: EmpresaUpdate, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        
    emp_data = emp_in.dict(exclude_unset=True)
    if "csc_token" in emp_data and emp_data["csc_token"]:
        emp_data["csc_token"] = encrypt_data(emp_data["csc_token"])
        
    for key, value in emp_data.items():
        setattr(empresa, key, value)
        
    # Sincronizar dados atualizados com ACBr (sem fallback simulado)
    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.sincronizar_empresa_acbr(empresa)
    empresa.acbr_sincronizado = ok
    if ok:
        empresa.acbr_ultimo_status = res.get("motivo") or res.get("status") or "Sincronizado"
    else:
        empresa.acbr_ultimo_status = f"Erro sync: {res.get('erro') or res.get('status_code') or res}"

    session.add(empresa)
    session.commit()
    session.refresh(empresa)

    return format_empresa_response(empresa)

@router.delete("/{empresa_id}")
def deletar_empresa(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    session.delete(empresa)
    session.commit()
    return {"ok": True}

@router.post("/{empresa_id}/certificado", response_model=EmpresaResponse)
async def upload_certificado(
    empresa_id: int,
    file: UploadFile = File(...),
    senha: str = Form(...),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        
    from app.services.certificado_service import save_certificado_file, parse_certificado
    
    # Salvar arquivo fisicamente
    file_path = save_certificado_file(empresa.id, file)
    
    # Validar senha e ler metadados
    dados_cert = parse_certificado(file_path, senha)
    
    # Criptografar senha e salvar base64 no banco
    empresa.certificado_base64 = dados_cert["base64"]
    empresa.certificado_senha = encrypt_data(senha)
    empresa.certificado_vencimento = dados_cert["vencimento"]
    empresa.certificado_emissor = dados_cert["emissor"]
    empresa.certificado_sujeito = dados_cert["sujeito"]
    
    # Transmitir e vincular certificado à ACBr API (sem simulação em homologação)
    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.enviar_certificado_acbr(empresa, dados_cert["base64"], senha)
    empresa.acbr_sincronizado = ok
    if ok:
        empresa.acbr_ultimo_status = f"Certificado: {res.get('motivo') or res.get('status') or 'Ativo no ACBr'}"
    else:
        empresa.acbr_ultimo_status = f"Erro certificado: {res.get('erro') or res.get('status_code') or res}"

    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    
    return format_empresa_response(empresa)

@router.post("/{empresa_id}/sincronizar-acbr", response_model=EmpresaResponse)
async def sincronizar_acbr(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    """Força o teste e sincronização cadastral + certificado com a ACBr API."""
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        
    acbr_service = ACBrAPIService()
    ok_emp, res_emp = await acbr_service.sincronizar_empresa_acbr(empresa)

    if ok_emp:
        status_msg = res_emp.get("motivo") or res_emp.get("status") or "Dados sincronizados"
    else:
        status_msg = f"Erro sync: {res_emp.get('erro') or res_emp.get('status_code') or res_emp}"

    if empresa.certificado_base64 and empresa.certificado_senha:
        senha_descriptografada = decrypt_data(empresa.certificado_senha)
        ok_cert, res_cert = await acbr_service.enviar_certificado_acbr(empresa, empresa.certificado_base64, senha_descriptografada)
        ok_emp = ok_emp and ok_cert
        if ok_cert:
            status_msg += f" | Certificado: {res_cert.get('motivo') or res_cert.get('status') or 'Ativo'}"
        else:
            status_msg += f" | Erro cert: {res_cert.get('erro') or res_cert.get('status_code') or res_cert}"

    empresa.acbr_sincronizado = ok_emp
    empresa.acbr_ultimo_status = status_msg
    session.add(empresa)
    session.commit()
    session.refresh(empresa)
    
    return format_empresa_response(empresa)

