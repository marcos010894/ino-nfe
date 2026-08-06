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
from app.schemas.nota import NotaCreate, NotaResponse, NotaCancelar, InutilizacaoRequest
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

    # 4. Reservar próximo nNF sequencial por (empresa, modelo, serie).
    # SEFAZ exige sequência ascendente; nNF aleatório causa cStat 204/539 em prod.
    # Uso `MAX(numero) + 1`; se não houver nota anterior, começa em 1.
    # Nota: em ambiente multi-worker, isso deveria ser um SELECT ... FOR UPDATE dentro
    # de transação — no momento o servidor é single-worker, então basta o MAX.
    modelo_int = int(nota_in.modelo)
    # Série ativa vem da empresa — cliente pode trocá-la via UI (ex: abandonar série 1
    # com gaps e recomeçar em série 2 sem precisar inutilizar milhares de números).
    SERIE_PADRAO = empresa.serie_nfe if modelo_int == 55 else empresa.serie_nfce
    ultimo_numero = session.exec(
        select(Nota.numero)
        .where(
            Nota.empresa_id == empresa_id,
            Nota.modelo == str(modelo_int),
            Nota.serie == SERIE_PADRAO,
            Nota.numero.is_not(None),
        )
        .order_by(Nota.numero.desc())
    ).first()
    proximo_numero = (ultimo_numero or 0) + 1

    # 5. Instanciar o serviço ACBr e montar o payload
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_nfce(
            empresa, regra, venda_data,
            modelo=modelo_int, numero=proximo_numero, serie=SERIE_PADRAO,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 6. Criar registro inicial da nota ou usar o rascunho.
    # Persistir `numero` e `serie` ANTES do envio garante que, mesmo se a SEFAZ
    # rejeitar, o número fica marcado como "queimado" no banco — pronto pra ir
    # à fila de inutilização (Etapa G do MVP).
    if nota_in.rascunho_id:
        nova_nota = session.get(Nota, nota_in.rascunho_id)
        if not nova_nota or nova_nota.usuario_id != current_user.id:
            raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
        nova_nota.empresa_id = empresa_id
        nova_nota.modelo = nota_in.modelo
        nova_nota.status = "processando"
        nova_nota.valor_total = valor_total
        nova_nota.json_venda = nota_in.json_venda
        nova_nota.payload_enviado = json.dumps(payload)
        nova_nota.numero = proximo_numero
        nova_nota.serie = SERIE_PADRAO
        nova_nota.atualizado_em = datetime.utcnow()
    else:
        nova_nota = Nota(
            empresa_id=empresa_id,
            usuario_id=current_user.id,
            modelo=nota_in.modelo,
            status="processando",
            valor_total=valor_total,
            json_venda=nota_in.json_venda,
            payload_enviado=json.dumps(payload),
            numero=proximo_numero,
            serie=SERIE_PADRAO,
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
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nova_nota.serie = resposta.get("serie")
        # Reconciliar o campo `modelo` da nota com o prefixo do id da ACBr — fonte de verdade
        # é a rota que a ACBr efetivamente processou, não o valor que o cliente pediu.
        if nova_nota.acbr_id:
            if nova_nota.acbr_id.startswith("nfc_"):
                nova_nota.modelo = "65"
            elif nova_nota.acbr_id.startswith("nfe_"):
                nova_nota.modelo = "55"

        # URLs de download proxy locais
        nova_nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
    elif status == "processando":
        # Se for NF-e processando, guardamos o id da ACBr + chave temporária se vier ou a referência
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso") or payload.get("referencia")
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nova_nota.serie = resposta.get("serie") or 1
        
        # PDFs/XMLs proxies temporários
        nova_nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
    else:
        aut = resposta.get("autorizacao") or {}
        err = resposta.get("error") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("motivo")
            or resposta.get("mensagem")
            or (resposta.get("erro") if isinstance(resposta.get("erro"), str) else None)
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        # Achatar motivo/cstat no topo do JSON persistido — evita que a UI mostre "{}"
        # quando lê só o nível raiz. Consumers podem ler `motivo_status`/`codigo_status`
        # direto sem descer no `autorizacao`.
        resposta = {**resposta, "motivo_status": motivo, "codigo_status": cstat}
        nova_nota.resposta_integradora = json.dumps(resposta)
        # id/chave também vêm na rejeição — guardar para diagnóstico
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        print(f"Nota Rejeitada ID {nova_nota.id}: cStat {cstat} — {motivo}")

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
    if not nota.acbr_id:
        raise HTTPException(status_code=400, detail="Nota não possui id da ACBr registrado — impossível cancelar via API.")
    # Modelo real vem do prefixo do id da ACBr (o service ainda decide, mas passamos por clareza).
    modelo = 55 if nota.acbr_id.startswith("nfe_") else 65
    sucesso, resposta = await acbr_service.cancelar_nfce(nota.acbr_id, cancel_in.justificativa, modelo=modelo)

    if sucesso:
        nota.status = "cancelada"
        nota.resposta_integradora = json.dumps(resposta)
        nota.atualizado_em = datetime.utcnow()
        session.add(nota)
        session.commit()
        session.refresh(nota)
        return nota
    else:
        aut = resposta.get("autorizacao") or {}
        err = resposta.get("error") or {}
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("motivo")
            or resposta.get("mensagem")
            or (resposta.get("erro") if isinstance(resposta.get("erro"), str) else None)
            or "Erro ao cancelar nota na SEFAZ"
        )
        prefixo = f"cStat {cstat}: " if cstat else ""
        raise HTTPException(status_code=400, detail=f"Falha ao cancelar nota na SEFAZ: {prefixo}{motivo}")


@router.post("/inutilizacoes")
async def inutilizar_faixa(
    empresa_id: int,
    body: InutilizacaoRequest,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Inutiliza uma faixa de numeração fiscal (Etapa G do MVP).

    Uso típico: número gerado no sistema mas nunca autorizado pela SEFAZ. Declarar
    como inutilizado fecha o livro fiscal sem gerar buracos que o auditor questione.
    """
    empresa = _verificar_empresa(empresa_id, session, current_user)

    if body.modelo not in ("55", "65"):
        raise HTTPException(status_code=400, detail="modelo deve ser '55' (NF-e) ou '65' (NFC-e).")
    if body.numero_inicial < 1 or body.numero_final < body.numero_inicial:
        raise HTTPException(status_code=400, detail="numero_final deve ser >= numero_inicial (ambos > 0).")
    if body.numero_final - body.numero_inicial > 999:
        # Limite prático: SEFAZ aceita até 999 num único lote de inutilização.
        raise HTTPException(status_code=400, detail="Faixa maior que 1000 números por lote não é permitida pela SEFAZ.")
    if len(body.justificativa) < 15:
        raise HTTPException(status_code=400, detail="Justificativa deve ter no mínimo 15 caracteres.")

    ano = body.ano or datetime.utcnow().year
    acbr = ACBrAPIService()
    ok, resposta = await acbr.inutilizar_faixa(
        cnpj=empresa.cnpj,
        ano=ano,
        serie=body.serie,
        numero_inicial=body.numero_inicial,
        numero_final=body.numero_final,
        justificativa=body.justificativa,
        modelo=int(body.modelo),
    )

    if not ok:
        err = resposta.get("error") or {}
        aut = resposta.get("autorizacao") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("erro")
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        prefixo = f"cStat {cstat}: " if cstat else ""
        raise HTTPException(status_code=400, detail=f"Falha ao inutilizar na SEFAZ: {prefixo}{motivo}")

    return {"ok": True, "ambiente": acbr.env, "modelo": body.modelo, "resposta": resposta}


@router.post("/inutilizacoes/auto")
async def inutilizar_gap_ultima_emissao(
    empresa_id: int,
    modelo: str,
    serie: int = 1,
    justificativa: str = "Correcao de sequencia por gap na numeracao do sistema emissor",
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Fecha o gap entre a última nota autorizada e a penúltima da mesma (modelo, série).

    Regra: pega as duas últimas notas AUTORIZADAS (ordenadas por `numero` desc) e
    inutiliza a faixa `(penúltima.numero + 1) .. (última.numero - 1)`. Cobre o cenário
    comum do sistema ter usado `random.randint` antes de virar sequencial.

    SEFAZ limita cada inutilização a 999 números por lote; se o gap for maior, o
    endpoint devolve 400 pedindo pra usar a rota manual em blocos.
    """
    empresa = _verificar_empresa(empresa_id, session, current_user)

    if modelo not in ("55", "65"):
        raise HTTPException(status_code=400, detail="modelo deve ser '55' (NF-e) ou '65' (NFC-e).")
    if len(justificativa) < 15:
        raise HTTPException(status_code=400, detail="Justificativa deve ter no mínimo 15 caracteres.")

    ultimas = session.exec(
        select(Nota)
        .where(
            Nota.empresa_id == empresa_id,
            Nota.modelo == modelo,
            Nota.serie == serie,
            Nota.status.in_(["autorizada", "cancelada"]),
            Nota.numero.is_not(None),
        )
        .order_by(Nota.numero.desc())
    ).all()

    if len(ultimas) < 2:
        raise HTTPException(
            status_code=400,
            detail="Precisa de pelo menos duas notas autorizadas/canceladas nessa (modelo, série) pra calcular o gap.",
        )

    ultima, penultima = ultimas[0], ultimas[1]
    ini = penultima.numero + 1
    fin = ultima.numero - 1

    if fin < ini:
        return {
            "ok": True,
            "mensagem": f"Sem gap a inutilizar entre nNF {penultima.numero} e {ultima.numero}.",
            "numero_inicial": None,
            "numero_final": None,
        }

    if fin - ini + 1 > 999:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Gap {ini}-{fin} tem {fin - ini + 1} números — SEFAZ aceita no máximo 999 "
                f"por lote. Use POST /inutilizacoes manual em blocos, ex: {ini}-{ini + 998}."
            ),
        )

    ano = datetime.utcnow().year
    acbr = ACBrAPIService()
    ok, resposta = await acbr.inutilizar_faixa(
        cnpj=empresa.cnpj,
        ano=ano,
        serie=serie,
        numero_inicial=ini,
        numero_final=fin,
        justificativa=justificativa,
        modelo=int(modelo),
    )

    if not ok:
        err = resposta.get("error") or {}
        aut = resposta.get("autorizacao") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("erro")
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        prefixo = f"cStat {cstat}: " if cstat else ""
        raise HTTPException(status_code=400, detail=f"Falha ao inutilizar na SEFAZ: {prefixo}{motivo}")

    return {
        "ok": True,
        "ambiente": acbr.env,
        "modelo": modelo,
        "serie": serie,
        "numero_inicial": ini,
        "numero_final": fin,
        "penultima_nota_id": penultima.id,
        "ultima_nota_id": ultima.id,
        "resposta": resposta,
    }


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
        nota.acbr_id = resposta.get("id")
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        nota.numero = resposta.get("numero") or resposta.get("numeroNota")
        nota.serie = resposta.get("serie")
        nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/pdf"
        nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/xml"
        
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

    # 2. Criar o ZIP em memória — baixa XML/PDF direto da ACBr (nada de mock)
    zip_buffer = io.BytesIO()
    acbr_service = ACBrAPIService()
    falhas: list[str] = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for nota in notas_com_doc:
            chave = nota.chave_acesso or f"NOTA_SEM_CHAVE_{nota.id}"
            num = nota.numero or nota.id
            ser = nota.serie or 1
            filename_base = f"{chave}_n{num}_s{ser}"
            # Modelo real vem do prefixo do id da ACBr (`nfc_` = 65, `nfe_` = 55).
            # Isso protege contra divergências históricas entre `nota.modelo` e a rota usada.
            if nota.acbr_id and nota.acbr_id.startswith("nfc_"):
                modelo = 65
            elif nota.acbr_id and nota.acbr_id.startswith("nfe_"):
                modelo = 55
            else:
                modelo = 65 if nota.modelo == "65" else 55

            if not nota.acbr_id:
                falhas.append(f"{filename_base}: sem acbr_id (nota não foi emitida via ACBr) — XML/PDF indisponíveis")
                continue

            if incluir in ["xml", "ambos"]:
                ok, xml_data = await acbr_service.baixar_xml(nota.acbr_id, modelo=modelo)
                if ok:
                    zip_file.writestr(f"{filename_base}.xml", xml_data)
                else:
                    falhas.append(f"{filename_base}.xml: ACBr rejeitou — {xml_data}")

            if incluir in ["pdf", "ambos"]:
                ok, pdf_data = await acbr_service.baixar_pdf(nota.acbr_id, modelo=modelo)
                if ok:
                    zip_file.writestr(f"{filename_base}.pdf", pdf_data)
                else:
                    falhas.append(f"{filename_base}.pdf: ACBr rejeitou — {pdf_data}")


        if falhas:
            zip_file.writestr("RELATORIO_FALHAS.txt", "\n".join(falhas).encode("utf-8"))

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

    if not nota.acbr_id:
        raise HTTPException(status_code=400, detail="Nota não possui id da ACBr — XML indisponível.")

    # Modelo real vem do prefixo do id da ACBr (`nfc_` = 65, `nfe_` = 55).
    # Isso protege contra divergências históricas entre `nota.modelo` e a rota usada.
    if nota.acbr_id and nota.acbr_id.startswith("nfc_"):
        modelo = 65
    elif nota.acbr_id and nota.acbr_id.startswith("nfe_"):
        modelo = 55
    else:
        modelo = 65 if nota.modelo == "65" else 55
    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.baixar_xml(nota.acbr_id, modelo=modelo)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar XML na ACBr: {res}")

    chave = nota.chave_acesso or nota.acbr_id
    return StreamingResponse(
        io.BytesIO(res),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={chave}.xml"},
    )


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

    if not nota.acbr_id:
        raise HTTPException(status_code=400, detail="Nota não possui id da ACBr — DANFE indisponível.")

    # Modelo real vem do prefixo do id da ACBr (`nfc_` = 65, `nfe_` = 55).
    # Isso protege contra divergências históricas entre `nota.modelo` e a rota usada.
    if nota.acbr_id and nota.acbr_id.startswith("nfc_"):
        modelo = 65
    elif nota.acbr_id and nota.acbr_id.startswith("nfe_"):
        modelo = 55
    else:
        modelo = 65 if nota.modelo == "65" else 55
    acbr_service = ACBrAPIService()
    ok, res = await acbr_service.baixar_pdf(nota.acbr_id, modelo=modelo)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar DANFE na ACBr: {res}")

    chave = nota.chave_acesso or nota.acbr_id
    return StreamingResponse(
        io.BytesIO(res),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={chave}.pdf"},
    )


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

    # 1. Localizar o identificador que a ACBr aceita no path.
    # GET /nfe/{id} exige o id interno da ACBr (`nfe_xxx`), NÃO a chave nem a referência
    # do cliente. Passar chave/referência devolve 404 DfeNotFound e o polling nunca sai
    # de "processando". Usar `nota.acbr_id`; só cai em referencia/chave como último recurso.
    identificador = nota.acbr_id
    if not identificador and nota.payload_enviado:
        try:
            payload_data = json.loads(nota.payload_enviado)
            identificador = payload_data.get("referencia")
        except Exception:
            pass
    if not identificador:
        identificador = nota.chave_acesso

    if not identificador:
        raise HTTPException(status_code=400, detail="Referência da integradora não encontrada nesta nota.")

    # 2. Consultar integradora
    acbr_service = ACBrAPIService()
    status, resposta = await acbr_service.consultar_status_nfe(identificador)
    
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



