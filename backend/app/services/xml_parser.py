"""Parser de XML de NF-e autorizada para pré-preencher formulário de devolução.

Extrai emitente/destinatário/itens/tributos e sugere CFOP inverso por item.
Usa xml.etree (stdlib, sem dependência extra).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional


NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


def _text(elem: Optional[ET.Element], path: str) -> Optional[str]:
    if elem is None:
        return None
    node = elem.find(path, NS)
    if node is None:
        return None
    return (node.text or "").strip() or None


def _float(elem: Optional[ET.Element], path: str, default: float = 0.0) -> float:
    val = _text(elem, path)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def cfop_inverso(
    cfop_original: Optional[str],
    uf_emit: Optional[str] = None,
    uf_dest: Optional[str] = None,
) -> Optional[str]:
    """Sugere CFOP de devolução a partir do CFOP de venda, respeitando UF.

    Regra geral: troca a primeira classe do CFOP (saída ↔ entrada).
    5xxx (saída interna)       → 1xxx (entrada interna)
    6xxx (saída interestadual) → 2xxx (entrada interestadual)
    7xxx (saída exterior)      → 3xxx (entrada exterior)

    Se `uf_emit` e `uf_dest` forem passados, corrige a classe conforme a UF:
    - UF iguais  → força classe 1 (entrada) ou 5 (saída) conforme direção
    - UF difere  → força classe 2 (entrada) ou 6 (saída)

    Sem UF: mantém comportamento antigo (só troca classe do CFOP original).
    """
    if not cfop_original or len(cfop_original) != 4 or not cfop_original.isdigit():
        return None

    mapa_direto = {
        "5101": "1201", "5102": "1202", "5405": "1411",
        "5656": "1411", "5949": "1949",
        "6101": "2201", "6102": "2202", "6108": "2202",
        "6403": "2411", "6949": "2949",
    }
    if cfop_original in mapa_direto:
        candidato = mapa_direto[cfop_original]
    else:
        primeira = cfop_original[0]
        sufixo = cfop_original[1:]
        if primeira == "5":
            candidato = "1" + sufixo
        elif primeira == "6":
            candidato = "2" + sufixo
        elif primeira == "7":
            candidato = "3" + sufixo
        elif primeira in ("1", "2"):
            # CFOP original já é de entrada (ex: nota de compra sendo devolvida) — vai virar saída.
            candidato = "5" + sufixo if primeira == "1" else "6" + sufixo
        else:
            return None

    # Se UF foi passada, ajusta a classe conforme direção
    if uf_emit and uf_dest:
        uf_emit_up = uf_emit.strip().upper()
        uf_dest_up = uf_dest.strip().upper()
        if uf_emit_up and uf_dest_up:
            interestadual = uf_emit_up != uf_dest_up
            primeira = candidato[0]
            sufixo = candidato[1:]
            if primeira == "1" and interestadual:
                candidato = "2" + sufixo
            elif primeira == "2" and not interestadual:
                candidato = "1" + sufixo
            elif primeira == "5" and interestadual:
                candidato = "6" + sufixo
            elif primeira == "6" and not interestadual:
                candidato = "5" + sufixo
    return candidato


def _extrair_destinatario_de_emitente(root: ET.Element) -> dict:
    """Quando a loja emite devolução de compra, o destinatário da nota nova
    é o emitente da nota original.
    """
    emit = root.find(".//n:emit", NS)
    if emit is None:
        return {}
    return {
        "cnpj": _text(emit, "n:CNPJ"),
        "cpf": _text(emit, "n:CPF"),
        "nome": _text(emit, "n:xNome") or "",
        "ie": _text(emit, "n:IE"),
        "logradouro": _text(emit, "n:enderEmit/n:xLgr"),
        "numero": _text(emit, "n:enderEmit/n:nro"),
        "complemento": _text(emit, "n:enderEmit/n:xCpl"),
        "bairro": _text(emit, "n:enderEmit/n:xBairro"),
        "cep": _text(emit, "n:enderEmit/n:CEP"),
        "municipio": _text(emit, "n:enderEmit/n:xMun"),
        "codigo_municipio": _text(emit, "n:enderEmit/n:cMun"),
        "uf": _text(emit, "n:enderEmit/n:UF"),
    }


def _extrair_itens(
    root: ET.Element,
    uf_emit: Optional[str] = None,
    uf_dest: Optional[str] = None,
) -> list:
    itens = []
    for det in root.findall(".//n:det", NS):
        prod = det.find("n:prod", NS)
        imposto = det.find("n:imposto", NS)
        if prod is None:
            continue

        cfop_orig = _text(prod, "n:CFOP")
        cfop_dev = cfop_inverso(cfop_orig, uf_emit, uf_dest) or (cfop_orig or "")

        # ICMS — tenta CST (regime normal) e CSOSN (Simples)
        cst_csosn = None
        icms_aliq = None
        icms_node = imposto.find("n:ICMS", NS) if imposto is not None else None
        if icms_node is not None:
            for child in list(icms_node):
                cst_csosn = (child.findtext("n:CST", namespaces=NS)
                             or child.findtext("n:CSOSN", namespaces=NS))
                aliq_txt = child.findtext("n:pICMS", namespaces=NS)
                if aliq_txt:
                    try:
                        icms_aliq = float(aliq_txt)
                    except ValueError:
                        pass
                if cst_csosn:
                    break

        # PIS/COFINS — CST e alíquota
        pis_cst = None
        pis_aliq = None
        if imposto is not None:
            pis_node = imposto.find("n:PIS", NS)
            if pis_node is not None:
                for child in list(pis_node):
                    pis_cst = child.findtext("n:CST", namespaces=NS)
                    aliq = child.findtext("n:pPIS", namespaces=NS)
                    if aliq:
                        try:
                            pis_aliq = float(aliq)
                        except ValueError:
                            pass
                    if pis_cst:
                        break

        cofins_cst = None
        cofins_aliq = None
        if imposto is not None:
            cofins_node = imposto.find("n:COFINS", NS)
            if cofins_node is not None:
                for child in list(cofins_node):
                    cofins_cst = child.findtext("n:CST", namespaces=NS)
                    aliq = child.findtext("n:pCOFINS", namespaces=NS)
                    if aliq:
                        try:
                            cofins_aliq = float(aliq)
                        except ValueError:
                            pass
                    if cofins_cst:
                        break

        # IPI — só existe em nota de Regime Normal com IPI destacado
        # Na devolução o CST vira 49 (retorno de mercadoria).
        ipi_cst = None
        ipi_aliq = None
        ipi_enq = None
        if imposto is not None:
            ipi_node = imposto.find("n:IPI", NS)
            if ipi_node is not None:
                ipi_enq = ipi_node.findtext("n:cEnq", namespaces=NS)
                for grupo_name in ("IPITrib", "IPINT"):
                    grupo = ipi_node.find(f"n:{grupo_name}", NS)
                    if grupo is not None:
                        orig_cst = grupo.findtext("n:CST", namespaces=NS)
                        # Devolução: CST vira 49 se original era tributado (00/50/99)
                        if orig_cst in ("00", "50", "99"):
                            ipi_cst = "49"
                        else:
                            ipi_cst = orig_cst
                        aliq = grupo.findtext("n:pIPI", namespaces=NS)
                        if aliq:
                            try:
                                ipi_aliq = float(aliq)
                            except ValueError:
                                pass
                        break

        itens.append({
            "codigo": _text(prod, "n:cProd") or "",
            "descricao": _text(prod, "n:xProd") or "",
            "ncm": _text(prod, "n:NCM") or "",
            "cfop": cfop_dev,
            "quantidade": _float(prod, "n:qCom"),
            "valor_unitario": _float(prod, "n:vUnCom"),
            "unidade": _text(prod, "n:uCom") or "UN",
            "cst_csosn": cst_csosn or "",
            "icms_aliquota": icms_aliq,
            "pis_cst": pis_cst,
            "pis_aliquota": pis_aliq,
            "cofins_cst": cofins_cst,
            "cofins_aliquota": cofins_aliq,
            "ipi_cst": ipi_cst,
            "ipi_aliquota": ipi_aliq,
            "ipi_enquadramento": ipi_enq,
        })
    return itens


def parse_nfe_xml(xml_bytes: bytes) -> dict:
    """Parseia XML de NF-e autorizada e retorna dict pronto pra preview.

    Assume que a NF-e original é uma nota emitida CONTRA a empresa (compra),
    então o emitente vira destinatário da devolução.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}")

    # Chave: pode estar em infNFe/@Id ("NFe" + 44 dígitos) ou em protNFe/infProt/chNFe
    chave = None
    inf_nfe = root.find(".//n:infNFe", NS)
    if inf_nfe is not None:
        raw_id = inf_nfe.get("Id") or ""
        if raw_id.startswith("NFe") and len(raw_id) == 47:
            chave = raw_id[3:]
    if not chave:
        chave = _text(root, ".//n:protNFe/n:infProt/n:chNFe")
    if not chave or len(chave) != 44 or not chave.isdigit():
        raise ValueError("Não foi possível extrair a chave de acesso (44 dígitos) do XML")

    nat_op_orig = _text(root, ".//n:ide/n:natOp") or "VENDA"
    natureza_devolucao = f"DEVOLUCAO - {nat_op_orig}"[:120]

    # UF emit vs dest da NF-e original — usado pra corrigir CFOP interna/interestadual
    uf_emit_orig = _text(root, ".//n:emit/n:enderEmit/n:UF")
    uf_dest_orig = _text(root, ".//n:dest/n:enderDest/n:UF")

    destinatario = _extrair_destinatario_de_emitente(root)
    itens = _extrair_itens(root, uf_emit=uf_emit_orig, uf_dest=uf_dest_orig)
    valor_total = _float(root, ".//n:total/n:ICMSTot/n:vNF")

    return {
        "chave_referenciada": chave,
        "natureza_operacao_sugerida": natureza_devolucao,
        "destinatario": destinatario,
        "itens": itens,
        "valor_total_original": valor_total,
    }
