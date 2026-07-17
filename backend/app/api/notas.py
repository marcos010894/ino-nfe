from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from typing import List, Optional
import json
from datetime import datetime
import zipfile
import io
import httpx
from app.models.database import get_session
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.models.nota import Nota
from app.models.usuario import Usuario
from app.schemas.nota import NotaCreate, NotaResponse, NotaCancelar
from app.api.auth import get_current_user
from app.services.acbr_api import ACBrAPIService

router = APIRouter(prefix="/empresas/{empresa_id}/notas", tags=["Notas Fiscais"])

def _verificar_empresa(empresa_id: int, session: Session, current_user: Usuario) -> Empresa:
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return empresa

@router.get("/", response_model=List[NotaResponse])
def listar_notas(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    notas = session.exec(select(Nota).where(Nota.empresa_id == empresa_id).order_by(Nota.criado_em.desc())).all()
    return notas

@router.post("/", response_model=NotaResponse)
async def criar_e_transmitir_nota(
    empresa_id: int, 
    nota_in: NotaCreate, 
    session: Session = Depends(get_session), 
    current_user: Usuario = Depends(get_current_user)
):
    empresa = _verificar_empresa(empresa_id, session, current_user)
    
    # 1. Carregar a regra fiscal padrão da empresa
    regra = session.exec(
        select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id, RegraFiscal.padrao == True)
    ).first()
    
    # Se não tiver padrão, pega a primeira encontrada
    if not regra:
        regra = session.exec(
            select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)
        ).first()
        
    if not regra:
        raise HTTPException(status_code=400, detail="Nenhuma regra fiscal cadastrada para esta empresa. Por favor, crie uma antes de emitir.")

    # 2. Parsear JSON de venda colado
    try:
        venda_data = json.loads(nota_in.json_venda)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de JSON de venda inválido.")

    # 3. Validar se o JSON tem itens e totais básicos
    if not venda_data.get("itens"):
        raise HTTPException(status_code=400, detail="O JSON de venda precisa conter ao menos um item em 'itens'.")

    # Calcular valor total
    itens = venda_data.get("itens", [])
    v_prod = sum(float(item.get("quantidade", 0)) * float(item.get("valor_unitario", 0)) for item in itens)
    v_desc = float(venda_data.get("desconto", 0.0))
    valor_total = round(v_prod - v_desc, 2)

    # 4. Instanciar o serviço ACBr e montar o payload
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_nfce(empresa, regra, venda_data, modelo=int(nota_in.modelo))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 5. Criar registro inicial da nota como rascunho
    nova_nota = Nota(
        empresa_id=empresa_id,
        modelo=nota_in.modelo,
        status="processando",
        valor_total=valor_total,
        json_venda=nota_in.json_venda,
        payload_enviado=json.dumps(payload),
        criado_em=datetime.utcnow(),
        atualizado_em=datetime.utcnow()
    )
    
    session.add(nova_nota)
    session.commit()
    session.refresh(nova_nota)

    # 6. Transmitir para a ACBr API
    if nota_in.modelo == "55":
        status, resposta = await acbr_service.transmitir_nfe(payload)
    else:
        status, resposta = await acbr_service.transmitir_nfce(payload)
    
    # 7. Tratar retorno da ACBr API
    nova_nota.status = status
    nova_nota.resposta_integradora = json.dumps(resposta)
    nova_nota.atualizado_em = datetime.utcnow()
    
    if status == "autorizada":
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nova_nota.serie = resposta.get("serie")
        
        # URLs de download proxy locais
        nova_nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
    elif status == "processando":
        # Se for NF-e processando, guardamos a chave temporária se vier ou a referência
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso") or payload.get("referencia")
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nova_nota.serie = resposta.get("serie") or 1
        
        # PDFs/XMLs proxies temporários
        nova_nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
    else:
        motivo = resposta.get("motivo") or resposta.get("mensagem") or resposta.get("erro", "Rejeição desconhecida")
        logger_err = f"Nota Rejeitada ID {nova_nota.id}: {motivo}"
        print(logger_err)

    session.add(nova_nota)
    session.commit()
    session.refresh(nova_nota)
    
    return nova_nota

@router.post("/{nota_id}/cancelar", response_model=NotaResponse)
async def cancelar_nota(
    empresa_id: int,
    nota_id: int,
    cancel_in: NotaCancelar,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    _verificar_empresa(empresa_id, session, current_user)
    
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
        
    if nota.status != "autorizada":
        raise HTTPException(status_code=400, detail="Apenas notas autorizadas podem ser canceladas.")
        
    if len(cancel_in.justificativa) < 15:
        raise HTTPException(status_code=400, detail="A justificativa de cancelamento deve ter no mínimo 15 caracteres.")
        
    acbr_service = ACBrAPIService()
    sucesso, resposta = await acbr_service.cancelar_nfce(nota.chave_acesso, cancel_in.justificativa)
    
    if sucesso:
        nota.status = "cancelada"
        nota.resposta_integradora = json.dumps(resposta)
        nota.atualizado_em = datetime.utcnow()
        session.add(nota)
        session.commit()
        session.refresh(nota)
        return nota
    else:
        motivo = resposta.get("motivo") or resposta.get("mensagem") or resposta.get("erro", "Erro ao cancelar nota na SEFAZ")
        raise HTTPException(status_code=400, detail=f"Falha ao cancelar nota na SEFAZ: {motivo}")

@router.put("/{nota_id}/reprocessar", response_model=NotaResponse)
async def reprocessar_nota(
    empresa_id: int,
    nota_id: int,
    nota_in: NotaCreate,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    empresa = _verificar_empresa(empresa_id, session, current_user)
    
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
        
    if nota.status != "rejeitada":
        raise HTTPException(status_code=400, detail="Apenas notas rejeitadas podem ser reprocessadas.")

    # 1. Carregar a regra fiscal padrão da empresa
    regra = session.exec(
        select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id, RegraFiscal.padrao == True)
    ).first()
    
    if not regra:
        regra = session.exec(
            select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)
        ).first()
        
    if not regra:
        raise HTTPException(status_code=400, detail="Nenhuma regra fiscal cadastrada para esta empresa.")

    # 2. Parsear JSON de venda corrigido
    try:
        venda_data = json.loads(nota_in.json_venda)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de JSON de venda inválido.")

    if not venda_data.get("itens"):
        raise HTTPException(status_code=400, detail="O JSON de venda precisa conter ao menos um item.")

    # Calcular totais
    itens = venda_data.get("itens", [])
    v_prod = sum(float(item.get("quantidade", 0)) * float(item.get("valor_unitario", 0)) for item in itens)
    v_desc = float(venda_data.get("desconto", 0.0))
    valor_total = round(v_prod - v_desc, 2)

    # 3. Montar novo payload
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_nfce(empresa, regra, venda_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 4. Atualizar registro da nota para reprocessando
    nota.status = "processando"
    nota.valor_total = valor_total
    nota.json_venda = nota_in.json_venda
    nota.payload_enviado = json.dumps(payload)
    nota.atualizado_em = datetime.utcnow()
    session.add(nota)
    session.commit()
    
    # 5. Transmitir nova tentativa
    status, resposta = await acbr_service.transmitir_nfce(payload)
    
    # 6. Atualizar resultado
    nota.status = status
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()
    
    if status == "autorizada":
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nota.serie = resposta.get("serie")
        nota.pdf_url = resposta.get("pdf") or resposta.get("pdfUrl") or f"https://hom.acbr.api.br/v1/nfce/{nota.chave_acesso}/pdf"
        nota.xml_url = resposta.get("xml") or resposta.get("xmlUrl") or f"https://hom.acbr.api.br/v1/nfce/{nota.chave_acesso}/xml"
        
    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota

@router.get("/exportar")
async def exportar_notas_lote(
    empresa_id: int,
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    incluir: str = Query("ambos"), # xml, pdf, ambos
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    empresa = _verificar_empresa(empresa_id, session, current_user)
    
    # 1. Buscar as notas com filtros aplicados
    query = select(Nota).where(Nota.empresa_id == empresa_id)
    if status:
        query = query.where(Nota.status == status)
    
    notas = session.exec(query).all()
    
    # Filtrar por data no Python para consistência de conversão de string de data do frontend
    if data_inicio:
        try:
            d_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
            notas = [n for n in notas if n.criado_em >= d_ini]
        except ValueError:
            pass
            
    if data_fim:
        try:
            d_fim = datetime.strptime(data_fim, "%Y-%m-%d")
            # Ajustar para o final do dia
            d_fim = d_fim.replace(hour=23, minute=59, second=59, microsecond=999999)
            notas = [n for n in notas if n.criado_em <= d_fim]
        except ValueError:
            pass

    # Filtrar apenas notas autorizadas ou canceladas que possuem documentos
    notas_com_doc = [n for n in notas if n.status in ["autorizada", "cancelada"]]
    
    if not notas_com_doc:
        raise HTTPException(status_code=400, detail="Nenhuma nota fiscal autorizada ou cancelada encontrada no lote filtrado.")

    # 2. Criar o ZIP em memória
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for nota in notas_com_doc:
            chave = nota.chave_acesso or f"NOTA_SEM_CHAVE_{nota.id}"
            num = nota.numero or nota.id
            ser = nota.serie or 1
            filename_base = f"{chave}_n{num}_s{ser}"
            
            # Adicionar XML
            if incluir in ["xml", "ambos"]:
                xml_data = b"<xml>Simulado</xml>"
                if nota.xml_url and "xml-simulado" not in nota.xml_url:
                    try:
                        async with httpx.AsyncClient() as client:
                            r = await client.get(nota.xml_url, timeout=5.0)
                            if r.status_code == 200:
                                xml_data = r.content
                    except Exception:
                        pass
                zip_file.writestr(f"{filename_base}.xml", xml_data)
                
            # Adicionar PDF
            if incluir in ["pdf", "ambos"]:
                pdf_data = b"%PDF-1.4 Mock PDF"
                if nota.pdf_url and "pdf-simulado" not in nota.pdf_url:
                    try:
                        async with httpx.AsyncClient() as client:
                            r = await client.get(nota.pdf_url, timeout=5.0)
                            if r.status_code == 200:
                                pdf_data = r.content
                    except Exception:
                        pass
                zip_file.writestr(f"{filename_base}.pdf", pdf_data)

    zip_buffer.seek(0)
    
    # 3. Stream do arquivo ZIP
    filename = f"notas_lote_{empresa.cnpj}_{datetime.now().strftime('%Y%m%d%H%M')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/{nota_id}/xml")
async def obter_xml_nota(
    empresa_id: int,
    nota_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    _verificar_empresa(empresa_id, session, current_user)
    
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
        
    if not nota.xml_url:
        raise HTTPException(status_code=404, detail="Arquivo XML não disponível para esta nota.")

    # Se for simulado
    is_simulado = False
    if nota.resposta_integradora:
        try:
            resp = json.loads(nota.resposta_integradora)
            if resp.get("simulado") or "simulado" in str(nota.xml_url):
                is_simulado = True
        except Exception:
            pass

    if is_simulado:
        # Retorna um XML dummy de testes
        mock_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
    <NFe>
        <infNFe Id="NFe{nota.chave_acesso}" versao="4.00">
            <ide>
                <cNF>{nota.chave_acesso[-8:] if nota.chave_acesso else '00000000'}</cNF>
                <nNF>{nota.numero}</nNF>
                <serie>{nota.serie}</serie>
            </ide>
            <total>
                <ICMSTot>
                    <vNF>{nota.valor_total}</vNF>
                </ICMSTot>
            </total>
        </infNFe>
    </NFe>
    <protNFe versao="4.00">
        <infProt>
            <chNFe>{nota.chave_acesso}</chNFe>
            <xMotivo>Autorizado o uso da NF-e (Simulado)</xMotivo>
        </infProt>
    </protNFe>
</nfeProc>"""
        return StreamingResponse(
            io.BytesIO(mock_xml.encode("utf-8")),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename={nota.chave_acesso}.xml"}
        )

    # Caso contrário, faz o fetch na ACBr API com o token
    acbr_service = ACBrAPIService()
    try:
        token = await acbr_service._get_access_token()
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            r = await client.get(nota.xml_url, headers=headers, timeout=10.0)
            if r.status_code == 200:
                return StreamingResponse(
                    io.BytesIO(r.content),
                    media_type="application/xml",
                    headers={"Content-Disposition": f"attachment; filename={nota.chave_acesso}.xml"}
                )
            else:
                raise HTTPException(status_code=r.status_code, detail=f"Erro ao buscar XML na integradora: {r.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha de comunicação com a integradora: {str(e)}")

@router.get("/{nota_id}/pdf")
async def obter_pdf_nota(
    empresa_id: int,
    nota_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    _verificar_empresa(empresa_id, session, current_user)
    
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
        
    if not nota.pdf_url:
        raise HTTPException(status_code=404, detail="Arquivo PDF não disponível para esta nota.")

    # Se for simulado
    is_simulado = False
    if nota.resposta_integradora:
        try:
            resp = json.loads(nota.resposta_integradora)
            if resp.get("simulado") or "simulado" in str(nota.pdf_url):
                is_simulado = True
        except Exception:
            pass

    if is_simulado:
        # Retorna um PDF dummy de testes
        mock_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 40 >>\nstream\nBT /F1 24 Tf 100 700 Td (DANFE NFC-e Simulado) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000060 00000 n\n0000000119 00000 n\n0000000213 00000 n\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n310\n%%EOF"
        return StreamingResponse(
            io.BytesIO(mock_pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={nota.chave_acesso}.pdf"}
        )

    # Caso contrário, faz o fetch na ACBr API com o token
    acbr_service = ACBrAPIService()
    try:
        token = await acbr_service._get_access_token()
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            r = await client.get(nota.pdf_url, headers=headers, timeout=10.0)
            if r.status_code == 200:
                return StreamingResponse(
                    io.BytesIO(r.content),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={nota.chave_acesso}.pdf"}
                )
            else:
                raise HTTPException(status_code=r.status_code, detail=f"Erro ao buscar PDF na integradora: {r.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha de comunicação com a integradora: {str(e)}")

@router.post("/{nota_id}/consultar-status", response_model=NotaResponse)
async def consultar_status_nota(
    empresa_id: int,
    nota_id: int,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    _verificar_empresa(empresa_id, session, current_user)
    
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
        
    if nota.status != "processando":
        return nota # Já concluída
        
    # 1. Recuperar a referência do payload enviado
    referencia = None
    if nota.payload_enviado:
        try:
            payload_data = json.loads(nota.payload_enviado)
            referencia = payload_data.get("referencia")
        except Exception:
            pass
            
    # Fallback se não achou referência
    if not referencia:
        referencia = nota.chave_acesso
        
    if not referencia:
        raise HTTPException(status_code=400, detail="Referência da integradora não encontrada nesta nota.")
        
    # 2. Consultar integradora
    acbr_service = ACBrAPIService()
    status, resposta = await acbr_service.consultar_status_nfe(referencia)
    
    # 3. Atualizar nota no banco
    nota.status = status
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()
    
    if status == "autorizada":
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso") or nota.chave_acesso
        nota.numero = resposta.get("numero") or resposta.get("numeroNota") or nota.numero
        nota.serie = resposta.get("serie") or nota.serie or 1
        
    session.add(nota)
    session.commit()
    session.refresh(nota)
    
    return nota



