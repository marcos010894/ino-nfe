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
from app.schemas.nota import (
    NotaCreate, NotaResponse, NotaCancelar, InutilizacaoRequest,
    DevolucaoCreate, DevolucaoPreviewResponse, NotaReenviar,
)
from app.api.auth import get_current_user
from app.api.integracao import _eh_denegacao, _eh_timeout_acbr
from app.services.acbr_api import ACBrAPIService
from app.services.xml_parser import parse_nfe_xml
from fastapi import UploadFile, File

router = APIRouter(prefix="/empresas/{empresa_id}/notas", tags=["Notas Fiscais"])

def _verificar_empresa(empresa_id: int, session: Session, current_user: Usuario) -> Empresa:
    empresa = session.get(Empresa, empresa_id)
    if not empresa or empresa.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    if empresa.deletada_em is not None:
        raise HTTPException(status_code=410, detail="Empresa deletada.")
    if empresa.bloqueada:
        raise HTTPException(status_code=403, detail="Empresa bloqueada — contate o suporte.")
    return empresa

@router.get("/", response_model=List[NotaResponse])
def listar_notas(empresa_id: int, session: Session = Depends(get_session), current_user: Usuario = Depends(get_current_user)):
    _verificar_empresa(empresa_id, session, current_user)
    notas = session.exec(select(Nota).where(Nota.empresa_id == empresa_id).order_by(Nota.criado_em.desc())).all()
    return notas


@router.get("/proximo-numero")
def obter_proximo_numero(
    empresa_id: int,
    modelo: int = Query(..., ge=55, le=65),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna o próximo nNF sugerido + série ativa (pra preview antes de emitir).

    Mesma lógica de `criar_e_transmitir_nota` sem transmitir. O operador pode
    aceitar o sugerido OU sobrescrever via `numero_override` no POST.
    """
    empresa = _verificar_empresa(empresa_id, session, current_user)
    if modelo not in (55, 65):
        raise HTTPException(status_code=400, detail="Modelo deve ser 55 ou 65.")

    serie = empresa.serie_nfe if modelo == 55 else empresa.serie_nfce
    ultimo_numero = session.exec(
        select(Nota.numero)
        .where(
            Nota.empresa_id == empresa_id,
            Nota.modelo == str(modelo),
            Nota.serie == serie,
            Nota.numero.is_not(None),
        )
        .order_by(Nota.numero.desc())
    ).first()

    # Mesma prioridade do POST: inicial_forcado > MAX+1 > 1.
    inicial_forcado = empresa.proximo_nnf_inicial_nfe if modelo == 55 else empresa.proximo_nnf_inicial_nfce
    if inicial_forcado:
        proximo = inicial_forcado
        fonte = "forcado"  # cadastro tem proximo_nnf_inicial_* setado
    elif ultimo_numero:
        proximo = ultimo_numero + 1
        fonte = "sequencial"
    else:
        proximo = 1
        fonte = "inicio_serie"

    return {
        "modelo": modelo,
        "serie": serie,
        "proximo_numero": proximo,
        "ultimo_emitido": ultimo_numero,
        "fonte": fonte,  # "forcado" | "sequencial" | "inicio_serie"
    }

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
    # Prioridade:
    # 1) numero_override (operador escolheu no modal de preview)
    # 2) empresa.proximo_nnf_inicial_* — "força uma vez": se setado, usa e ZERA
    #    depois. Serve pra migração de ERP e pra correção pontual pelo cadastro.
    # 3) ultimo_numero + 1 (MAX+1 sequencial)
    # 4) 1 (empresa sem histórico e sem inicial forçado)
    inicial_forcado = (empresa.proximo_nnf_inicial_nfe if modelo_int == 55
                       else empresa.proximo_nnf_inicial_nfce)
    consumiu_inicial = False
    if nota_in.numero_override:
        proximo_numero = nota_in.numero_override
    elif inicial_forcado:
        proximo_numero = inicial_forcado
        consumiu_inicial = True
    elif ultimo_numero:
        proximo_numero = ultimo_numero + 1
    else:
        proximo_numero = 1

    # Se consumiu o "força uma vez", zera pra próxima emissão cair no MAX+1.
    if consumiu_inicial:
        if modelo_int == 55:
            empresa.proximo_nnf_inicial_nfe = None
        else:
            empresa.proximo_nnf_inicial_nfce = None
        session.add(empresa)

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
        # Fallback pro proximo_numero/SERIE_PADRAO: se ACBr não devolve numero/serie
        # no top-level da resposta autorizada, a nota fica com numero=None e some do
        # MAX(numero)+1 — a próxima emissão propõe o mesmo nNF de novo (bug produção).
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota") or proximo_numero
        nova_nota.serie = resposta.get("serie") or SERIE_PADRAO
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
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota") or proximo_numero
        nova_nota.serie = resposta.get("serie") or SERIE_PADRAO
        # Timeout/erro comm ACBr: status real incerto. Marca pendente_consulta pra
        # travar a fila até uma consulta explícita ao SEFAZ resolver o veredito.
        if _eh_timeout_acbr(resposta):
            nova_nota.status = "pendente_consulta"

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
        # Denegação (110/301/302): SEFAZ consumiu o nNF mas trava reenvio.
        # Status próprio pra a fila seguir (nNF+1) sem oferecer botão de reenviar.
        if _eh_denegacao(cstat):
            nova_nota.status = "denegada"
        nova_nota.resposta_integradora = json.dumps(resposta)
        # id/chave também vêm na rejeição — guardar para diagnóstico
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        print(f"Nota {nova_nota.status.title()} ID {nova_nota.id}: cStat {cstat} — {motivo}")

    session.add(nova_nota)
    session.commit()
    session.refresh(nova_nota)

    return nova_nota


# ------------------------------------------------------------------
# Reenvio de nota REJEITADA — reusa o mesmo nNF/serie
# ------------------------------------------------------------------

def _aplicar_destinatario_reenvio(venda_data: dict, destinatario) -> dict:
    """Sobrescreve os campos de cliente/endereço do json_venda com os do body.

    Só atualiza os campos que vieram preenchidos no body — o resto do json_venda
    permanece intacto. Campos vazios ("") são tratados como "não enviado" e
    ignorados, pra não zerar dado válido do original.
    """
    if destinatario is None:
        return venda_data

    dest_dict = destinatario.model_dump(exclude_none=True)
    # Descartar strings vazias — pydantic aceita "" como valor válido, mas aqui
    # semanticamente significa "usuário não preencheu".
    dest_dict = {k: v for k, v in dest_dict.items() if not (isinstance(v, str) and v.strip() == "")}
    if not dest_dict:
        return venda_data

    cliente = dict(venda_data.get("cliente") or {})
    endereco = dict(cliente.get("endereco") or {})

    # Campos no nível do cliente
    for k in ("nome", "cpf", "cnpj", "email", "telefone"):
        if k in dest_dict:
            cliente[k] = dest_dict[k]

    # Campos no nível do endereço
    endereco_keys = ("logradouro", "numero", "complemento", "bairro", "cidade",
                      "uf", "cep", "codigo_municipio")
    for k in endereco_keys:
        if k in dest_dict:
            endereco[k] = dest_dict[k]

    if endereco:
        cliente["endereco"] = endereco
    venda_data["cliente"] = cliente
    return venda_data


@router.post("/{nota_id}/reenviar", response_model=NotaResponse)
async def reenviar_nota_rejeitada(
    empresa_id: int,
    nota_id: int,
    body: Optional[NotaReenviar] = None,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Reenvia uma nota REJEITADA reusando o mesmo nNF/serie.

    Objetivo: evitar furo na sequência numérica quando a SEFAZ rejeita a nota.
    O número fica "reservado" pra essa nota até virar autorizada, cancelada ou
    ser inutilizada — nunca é consumido por outra venda.

    Fluxo:
    - Só aceita nota com status="rejeitada".
    - Se `body.destinatario` vier preenchido, sobrescreve os campos correspondentes
      no `json_venda` salvo antes de remontar o payload.
    - Reusa `numero` e `serie` da nota original (não pega MAX+1).
    - Substitui o registro existente (não cria nota nova).
    """
    empresa = _verificar_empresa(empresa_id, session, current_user)

    # 1. Buscar a nota e validar
    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    if nota.status != "rejeitada":
        raise HTTPException(
            status_code=400,
            detail=f"Só é possível reenviar notas com status='rejeitada'. Status atual: '{nota.status}'."
        )
    if nota.numero is None:
        # Não deveria acontecer — o fluxo de criação persiste numero antes de transmitir.
        raise HTTPException(
            status_code=400,
            detail="Nota rejeitada sem número reservado. Impossível reenviar sem gerar furo."
        )

    # 2. Regra fiscal padrão (mesma lógica do POST /)
    regra = session.exec(
        select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id, RegraFiscal.padrao == True)
    ).first()
    if not regra:
        regra = session.exec(
            select(RegraFiscal).where(RegraFiscal.empresa_id == empresa_id)
        ).first()
    if not regra:
        raise HTTPException(status_code=400, detail="Nenhuma regra fiscal cadastrada para esta empresa.")

    # 3. Parsear json_venda salvo + aplicar overrides do destinatário
    try:
        venda_data = json.loads(nota.json_venda or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="json_venda salvo é inválido — impossível remontar payload.")

    if not venda_data.get("itens"):
        raise HTTPException(status_code=400, detail="json_venda salvo não tem itens.")

    venda_data = _aplicar_destinatario_reenvio(venda_data, body.destinatario if body else None)

    # 4. Recalcular valor_total (destinatário mudou, mas itens podem ter permanecido)
    itens = venda_data.get("itens", [])
    v_prod = sum(float(item.get("quantidade", 0)) * float(item.get("valor_unitario", 0)) for item in itens)
    v_desc = float(venda_data.get("desconto", 0.0))
    valor_total = round(v_prod - v_desc, 2)

    # 5. Remontar payload — REUSA numero/serie da nota original
    modelo_int = int(nota.modelo) if nota.modelo else 65
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_nfce(
            empresa, regra, venda_data,
            modelo=modelo_int, numero=nota.numero, serie=nota.serie or 1,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 6. Atualizar o registro da nota (não cria nova)
    nota.status = "processando"
    nota.valor_total = valor_total
    nota.json_venda = json.dumps(venda_data)
    nota.payload_enviado = json.dumps(payload)
    nota.atualizado_em = datetime.utcnow()
    # numero e serie ficam intactos — é o ponto do reenvio.
    session.add(nota)
    session.commit()
    session.refresh(nota)

    # 7. Transmitir
    if modelo_int == 55:
        status, resposta = await acbr_service.transmitir_nfe(payload)
    else:
        status, resposta = await acbr_service.transmitir_nfce(payload)

    # 8. Tratar retorno (mesmo shape do POST /)
    nota.status = status
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()

    if status == "autorizada":
        nota.acbr_id = resposta.get("id")
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        # numero/serie autoritativos da ACBr — mas devem casar com os que reservamos
        acbr_numero = resposta.get("numero") or resposta.get("numeroNota")
        if acbr_numero is not None:
            nota.numero = acbr_numero
        acbr_serie = resposta.get("serie")
        if acbr_serie is not None:
            nota.serie = acbr_serie
        if nota.acbr_id:
            if nota.acbr_id.startswith("nfc_"):
                nota.modelo = "65"
            elif nota.acbr_id.startswith("nfe_"):
                nota.modelo = "55"
        nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/pdf"
        nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/xml"
    elif status == "processando":
        nota.acbr_id = resposta.get("id")
        nota.chave_acesso = (
            resposta.get("chave") or resposta.get("chaveAcesso") or payload.get("referencia")
        )
        # Timeout/erro comm ACBr: SEFAZ pode ter recebido esse reenvio ou não.
        # Marca pendente_consulta pra ativar o fluxo de consulta por chave.
        if _eh_timeout_acbr(resposta):
            nota.status = "pendente_consulta"
        nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/pdf"
        nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/xml"
    else:
        # Rejeitada de novo — achata motivo/cstat no topo, mantém numero/serie.
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
        resposta = {**resposta, "motivo_status": motivo, "codigo_status": cstat}
        # Denegação (110/301/302) no reenvio: nNF foi consumido nessa
        # tentativa, não dá pra reenviar de novo. Marca denegada.
        if _eh_denegacao(cstat):
            nota.status = "denegada"
        nota.resposta_integradora = json.dumps(resposta)
        nota.acbr_id = resposta.get("id") or nota.acbr_id
        print(f"Reenvio da Nota ID {nota.id} {nota.status}: cStat {cstat} — {motivo}")

    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota


# ------------------------------------------------------------------
# NF-e de DEVOLUÇÃO (mod 55, finNFe=4)
# ------------------------------------------------------------------

@router.post("/devolucao/preview", response_model=DevolucaoPreviewResponse)
async def preview_devolucao_upload(
    empresa_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Recebe o XML da NF-e original e devolve dados prontos pra popular o formulário."""
    _verificar_empresa(empresa_id, session, current_user)
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .xml")
    xml_bytes = await file.read()
    if len(xml_bytes) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="XML acima do limite (2 MB)")
    try:
        parsed = parse_nfe_xml(xml_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return parsed


@router.get("/devolucao/preview-chave", response_model=DevolucaoPreviewResponse)
async def preview_devolucao_por_chave(
    empresa_id: int,
    chave: str = Query(..., min_length=44, max_length=44),
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Busca uma nota já emitida no InnoFiscal pela chave, baixa XML da ACBr e parseia."""
    _verificar_empresa(empresa_id, session, current_user)
    if not chave.isdigit():
        raise HTTPException(status_code=400, detail="Chave deve ter 44 dígitos numéricos")

    nota = session.exec(
        select(Nota).where(Nota.chave_acesso == chave, Nota.status == "autorizada")
    ).first()
    if not nota or not nota.acbr_id:
        raise HTTPException(status_code=404, detail="Nota autorizada não encontrada pra essa chave")

    modelo_int = 55
    if nota.acbr_id.startswith("nfc_"):
        modelo_int = 65
    elif nota.acbr_id.startswith("nfe_"):
        modelo_int = 55

    acbr_service = ACBrAPIService()
    try:
        ok, xml_or_err = await acbr_service.baixar_xml(nota.acbr_id, modelo=modelo_int)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar XML na ACBr: {exc}")

    if not ok or not isinstance(xml_or_err, (bytes, bytearray)):
        detalhe = xml_or_err if isinstance(xml_or_err, dict) else {"erro": str(xml_or_err)}
        raise HTTPException(status_code=502, detail=f"ACBr não devolveu XML: {detalhe}")

    try:
        parsed = parse_nfe_xml(bytes(xml_or_err))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return parsed


@router.post("/devolucao", response_model=NotaResponse)
async def emitir_devolucao(
    empresa_id: int,
    dados: DevolucaoCreate,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Emite NF-e mod 55 com finNFe=4 (devolução) e NFref → chave da nota original."""
    empresa = _verificar_empresa(empresa_id, session, current_user)

    # Validações
    if not dados.chave_referenciada.isdigit():
        raise HTTPException(status_code=400, detail="chave_referenciada deve ter 44 dígitos")

    # Reservar próximo nNF sequencial (mod 55, série da empresa)
    SERIE_PADRAO = empresa.serie_nfe or 1
    ultimo_numero = session.exec(
        select(Nota.numero)
        .where(
            Nota.empresa_id == empresa_id,
            Nota.modelo == "55",
            Nota.serie == SERIE_PADRAO,
            Nota.numero.is_not(None),
        )
        .order_by(Nota.numero.desc())
    ).first()
    # Devolução é sempre mod 55 — segue mesma prioridade do POST /notas/ (inicial
    # forçado > MAX+1 > 1) e consome o inicial se usar.
    inicial_forcado_dev = empresa.proximo_nnf_inicial_nfe
    consumiu_inicial_dev = False
    if inicial_forcado_dev:
        proximo_numero = inicial_forcado_dev
        consumiu_inicial_dev = True
    elif ultimo_numero:
        proximo_numero = ultimo_numero + 1
    else:
        proximo_numero = 1
    if consumiu_inicial_dev:
        empresa.proximo_nnf_inicial_nfe = None
        session.add(empresa)

    # Montar payload
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_devolucao(
            empresa, dados, numero=proximo_numero, serie=SERIE_PADRAO,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao montar payload de devolução: {e}")

    # Localizar nota original no próprio InnoFiscal (opcional)
    nota_original = session.exec(
        select(Nota).where(Nota.chave_acesso == dados.chave_referenciada)
    ).first()

    valor_total = sum(float(i.quantidade) * float(i.valor_unitario) for i in dados.itens)

    nova_nota = Nota(
        empresa_id=empresa_id,
        usuario_id=current_user.id,
        modelo="55",
        status="processando",
        valor_total=round(valor_total, 2),
        json_venda=json.dumps({
            "chave_referenciada": dados.chave_referenciada,
            "motivo": dados.motivo,
            "destinatario": dados.destinatario.model_dump(),
            "itens": [i.model_dump() for i in dados.itens],
        }),
        payload_enviado=json.dumps(payload),
        numero=proximo_numero,
        serie=SERIE_PADRAO,
        finalidade=4,
        nota_referenciada_chave=dados.chave_referenciada,
        nota_referenciada_id=(nota_original.id if nota_original else None),
        natureza_operacao=dados.natureza_operacao,
        criado_em=datetime.utcnow(),
        atualizado_em=datetime.utcnow(),
    )
    session.add(nova_nota)
    session.commit()
    session.refresh(nova_nota)

    # Transmitir
    status, resposta = await acbr_service.transmitir_nfe(payload)

    nova_nota.status = status
    nova_nota.resposta_integradora = json.dumps(resposta)
    nova_nota.atualizado_em = datetime.utcnow()

    if status == "autorizada":
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")
        nova_nota.numero = resposta.get("numero") or resposta.get("numeroNota") or proximo_numero
        nova_nota.serie = resposta.get("serie") or SERIE_PADRAO
        nova_nota.pdf_url = f"/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
    elif status == "processando":
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso") or payload.get("referencia")
        # Timeout na devolução: mesmo tratamento — pendente_consulta trava a fila.
        if _eh_timeout_acbr(resposta):
            nova_nota.status = "pendente_consulta"
        nova_nota.pdf_url = f"/empresas/{empresa_id}/notas/{nova_nota.id}/pdf"
        nova_nota.xml_url = f"/empresas/{empresa_id}/notas/{nova_nota.id}/xml"
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
        resposta = {**resposta, "motivo_status": motivo, "codigo_status": cstat}
        # Denegação em devolução: nNF de devolução consumido, marca denegada.
        if _eh_denegacao(cstat):
            nova_nota.status = "denegada"
        nova_nota.resposta_integradora = json.dumps(resposta)
        nova_nota.acbr_id = resposta.get("id")
        nova_nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso")

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


@router.post("/{nota_id}/inutilizar", response_model=NotaResponse)
async def inutilizar_nota_individual(
    empresa_id: int,
    nota_id: int,
    cancel_in: NotaCancelar,
    session: Session = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Inutiliza o nNF de UMA nota rejeitada/pendente_consulta — destrava a fila.

    ÚLTIMO RECURSO. A preferência é sempre reenviar corrigido (`/reenviar` reusa
    mesmo nNF). Só use quando o operador DESISTIR da venda — inutilização gera
    lastro fiscal permanente na SEFAZ.

    Gêmea JWT do `POST /integracao/inutilizar/{id}` (X-API-Key) — mesma lógica,
    só muda a autenticação. Existe pra frontend não precisar expor o token de
    integração no browser.
    """
    empresa = _verificar_empresa(empresa_id, session, current_user)

    nota = session.get(Nota, nota_id)
    if not nota or nota.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
    if nota.status not in ("rejeitada", "pendente_consulta"):
        raise HTTPException(
            status_code=400,
            detail=f"Só notas 'rejeitada' ou 'pendente_consulta' podem ser inutilizadas. Status atual: '{nota.status}'.",
        )
    if nota.numero is None:
        raise HTTPException(status_code=400, detail="Nota sem número reservado — nada a inutilizar.")
    if len(cancel_in.justificativa) < 15:
        raise HTTPException(status_code=400, detail="Justificativa deve ter no mínimo 15 caracteres.")

    modelo_int = 55 if nota.modelo == "55" else 65
    ano = (nota.criado_em or datetime.utcnow()).year

    acbr = ACBrAPIService()
    ok, resposta = await acbr.inutilizar_faixa(
        cnpj=empresa.cnpj,
        ano=ano,
        serie=nota.serie or 1,
        numero_inicial=nota.numero,
        numero_final=nota.numero,
        justificativa=cancel_in.justificativa,
        modelo=modelo_int,
    )

    if not ok:
        aut = resposta.get("autorizacao") or {}
        err = resposta.get("error") or {}
        motivo = (
            aut.get("motivo_status")
            or resposta.get("motivo_status")
            or err.get("message")
            or resposta.get("erro")
            or "Rejeição desconhecida"
        )
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or err.get("code")
        prefixo = f"cStat {cstat}: " if cstat else ""
        raise HTTPException(status_code=400, detail=f"SEFAZ recusou inutilização: {prefixo}{motivo}")

    nota.status = "inutilizada"
    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()
    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota


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

    # 3. Reservar próximo nNF/serie pelo cadastro atual da empresa — MESMO padrão
    # do POST /emitir (linhas 127-171). Bug histórico: essa rota chamava
    # `montar_payload_nfce(empresa, regra, venda_data)` sem numero/serie, caindo
    # em serie=1 default + nNF random.randint(1,999999) — reprocessou numa NFC-e
    # prod (id=113 nNF=160794 serie=1, cancelada em 2026-09-07).
    modelo_int = int(nota.modelo)
    SERIE_PADRAO = empresa.serie_nfe if modelo_int == 55 else empresa.serie_nfce
    ultimo_numero = session.exec(
        select(Nota.numero)
        .where(
            Nota.empresa_id == empresa_id,
            Nota.modelo == str(modelo_int),
            Nota.serie == SERIE_PADRAO,
            Nota.numero.is_not(None),
            Nota.id != nota.id,  # não conta ela mesma (rejeitada não queima nNF)
        )
        .order_by(Nota.numero.desc())
    ).first()
    inicial_forcado = (empresa.proximo_nnf_inicial_nfe if modelo_int == 55
                       else empresa.proximo_nnf_inicial_nfce)
    consumiu_inicial = False
    if nota_in.numero_override:
        proximo_numero = nota_in.numero_override
    elif inicial_forcado:
        proximo_numero = inicial_forcado
        consumiu_inicial = True
    elif ultimo_numero:
        proximo_numero = ultimo_numero + 1
    else:
        proximo_numero = 1
    if consumiu_inicial:
        if modelo_int == 55:
            empresa.proximo_nnf_inicial_nfe = None
        else:
            empresa.proximo_nnf_inicial_nfce = None
        session.add(empresa)

    # 4. Montar novo payload passando numero/serie explícitos
    acbr_service = ACBrAPIService()
    try:
        payload = acbr_service.montar_payload_nfce(
            empresa, regra, venda_data,
            modelo=modelo_int, numero=proximo_numero, serie=SERIE_PADRAO,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao gerar payload fiscal: {str(e)}")

    # 5. Atualizar registro da nota para reprocessando (queima nNF/serie antes do send)
    nota.status = "processando"
    nota.valor_total = valor_total
    nota.json_venda = nota_in.json_venda
    nota.payload_enviado = json.dumps(payload)
    nota.numero = proximo_numero
    nota.serie = SERIE_PADRAO
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
        # Fallback pro proximo_numero/SERIE_PADRAO — mesmo pattern do /emitir.
        nota.numero = resposta.get("numero") or resposta.get("numeroNota") or proximo_numero
        nota.serie = resposta.get("serie") or SERIE_PADRAO
        nota.pdf_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/pdf"
        nota.xml_url = f"http://localhost:8000/empresas/{empresa_id}/notas/{nota.id}/xml"
    else:
        # Denegação (110/301/302): nNF consumido, sem reenvio possível.
        aut = resposta.get("autorizacao") or {}
        cstat = aut.get("codigo_status") or resposta.get("codigo_status") or (resposta.get("error") or {}).get("code")
        if _eh_denegacao(cstat):
            nota.status = "denegada"
        elif status == "processando" and _eh_timeout_acbr(resposta):
            # Timeout na retransmissão: destino incerto, marca pendente_consulta.
            nota.status = "pendente_consulta"

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
        
    # Aceita processando (fila async normal) e pendente_consulta (timeout no envio,
    # destino incerto — SEFAZ pode ter recebido ou não). Terminais retornam como estão.
    if nota.status not in ("processando", "pendente_consulta"):
        return nota

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
    
    # 3. Atualizar nota no banco. Aplica denegação (cStat 110/301/302) e mantém
    # pendente_consulta se SEFAZ ainda não devolveu status definitivo.
    aut = resposta.get("autorizacao") or {}
    cstat = aut.get("codigo_status") or resposta.get("codigo_status")

    if _eh_denegacao(cstat):
        nota.status = "denegada"
    elif status in ("autorizada", "rejeitada"):
        nota.status = status
    # senão: SEFAZ não deu veredito ainda — preserva pendente_consulta/processando.

    nota.resposta_integradora = json.dumps(resposta)
    nota.atualizado_em = datetime.utcnow()

    if nota.status == "autorizada":
        nota.chave_acesso = resposta.get("chave") or resposta.get("chaveAcesso") or nota.chave_acesso
        nota.numero = resposta.get("numero") or resposta.get("numeroNota") or nota.numero
        nota.serie = resposta.get("serie") or nota.serie or 1

    session.add(nota)
    session.commit()
    session.refresh(nota)

    return nota



