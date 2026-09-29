"""Empacota XMLs/PDFs de notas fiscais em ZIP organizado + relatório PDF único.

Usado por:
- `GET /empresas/{id}/notas/exportar` (download direto pelo dono)
- `POST /empresas/{id}/contador/enviar` (email pro contador)
- Cron mensal dia N (mesmo caminho do envio manual)

V3.4 (ZIP em pastas): estrutura é `NFC-e/`, `NF-e/`, `Canceladas/` no root
do ZIP. Nota autorizada vai pra pasta do modelo; cancelada vai pra
`Canceladas/` (contador quer separar do que está válido).

V3.5 (PDF único): `RELATORIO.pdf` no root do ZIP com resumo do período +
tabela das notas. Gerado via reportlab.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.empresa import Empresa
from app.models.nota import Nota
from app.services.acbr_api import ACBrAPIService


# ---------------------------------------------------------------------------
# Datas / formatação
# ---------------------------------------------------------------------------

_MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def formatar_periodo(inicio: datetime, fim: datetime) -> str:
    """"01/09/2026 a 30/09/2026" — bate com o rótulo do frontend."""
    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


def formatar_periodo_mensal(inicio: datetime) -> str:
    """"Setembro/2026" — usado no assunto do e-mail pro contador."""
    return f"{_MESES_PT[inicio.month - 1].capitalize()}/{inicio.year}"


def _modelo_da_nota(nota: Nota) -> int:
    """Prefixo do acbr_id > coluna modelo (protege contra divergência histórica)."""
    if nota.acbr_id and nota.acbr_id.startswith("nfc_"):
        return 65
    if nota.acbr_id and nota.acbr_id.startswith("nfe_"):
        return 55
    return 65 if nota.modelo == "65" else 55


def _pasta_da_nota(nota: Nota) -> str:
    """Pasta destino dentro do ZIP. Cancelada tem pasta própria."""
    if nota.status == "cancelada":
        return "Canceladas"
    return "NFC-e" if _modelo_da_nota(nota) == 65 else "NF-e"


# ---------------------------------------------------------------------------
# Resultado do export
# ---------------------------------------------------------------------------


@dataclass
class ResumoExport:
    """Retorno de `preparar_lote` — mostrado no modal preview (V3.3) e usado
    no cabeçalho do RELATORIO.pdf."""
    qtd_nfce_autorizadas: int = 0
    qtd_nfe_autorizadas: int = 0
    qtd_canceladas: int = 0
    valor_total_autorizadas: float = 0.0
    empresa_nome: str = ""
    empresa_cnpj: str = ""
    periodo_label: str = ""
    notas_resumo: list[dict] = field(default_factory=list)  # p/ tabela do PDF e preview JSON

    @property
    def qtd_total(self) -> int:
        return self.qtd_nfce_autorizadas + self.qtd_nfe_autorizadas + self.qtd_canceladas


@dataclass
class LoteExportado:
    zip_bytes: bytes
    filename: str
    resumo: ResumoExport
    falhas: list[str]  # XMLs/PDFs que a ACBr recusou


# ---------------------------------------------------------------------------
# Preview (sem tocar na ACBr — só conta e resume)
# ---------------------------------------------------------------------------


def resumir(
    empresa: Empresa,
    notas: list[Nota],
    inicio: datetime,
    fim: datetime,
) -> ResumoExport:
    """Monta o `ResumoExport` só com dados locais — não bate na ACBr.

    Serve o modal preview (V3.3) que precisa mostrar contagem+valor antes de
    o usuário clicar "Baixar" (evita ZIP vazio ou surpresa)."""
    resumo = ResumoExport(
        empresa_nome=empresa.nome_fantasia or empresa.razao_social,
        empresa_cnpj=empresa.cnpj,
        periodo_label=formatar_periodo(inicio, fim),
    )
    for n in notas:
        modelo = _modelo_da_nota(n)
        if n.status == "cancelada":
            resumo.qtd_canceladas += 1
        elif n.status == "autorizada":
            if modelo == 65:
                resumo.qtd_nfce_autorizadas += 1
            else:
                resumo.qtd_nfe_autorizadas += 1
            resumo.valor_total_autorizadas += float(n.valor_total or 0)
        resumo.notas_resumo.append({
            "id": n.id,
            "numero": n.numero,
            "serie": n.serie,
            "modelo": modelo,
            "status": n.status,
            "criado_em": n.criado_em.isoformat() if n.criado_em else None,
            "valor_total": float(n.valor_total or 0),
            "chave_acesso": n.chave_acesso,
            "numero_venda": n.numero_venda,
        })
    return resumo


# ---------------------------------------------------------------------------
# PDF relatório único (V3.5)
# ---------------------------------------------------------------------------


def _gerar_relatorio_pdf(resumo: ResumoExport, notas: list[Nota]) -> bytes:
    """PDF resumo do lote. Título + cabeçalho + tabela + rodapé de contagem.

    Usa reportlab por ser puro Python. Tabela paginada automaticamente pelo
    SimpleDocTemplate quando estoura a página.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Relatório fiscal — {resumo.empresa_nome} — {resumo.periodo_label}",
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Relatório fiscal do período</b>", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>{resumo.empresa_nome}</b> — CNPJ {resumo.empresa_cnpj}", styles["Normal"]
    ))
    story.append(Paragraph(f"Período: {resumo.periodo_label}", styles["Normal"]))
    story.append(Spacer(1, 10))

    # Cabeçalho de contagens
    valor_fmt = f"R$ {resumo.valor_total_autorizadas:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    story.append(Paragraph(
        f"<b>NFC-e autorizadas:</b> {resumo.qtd_nfce_autorizadas} · "
        f"<b>NF-e autorizadas:</b> {resumo.qtd_nfe_autorizadas} · "
        f"<b>Canceladas:</b> {resumo.qtd_canceladas}",
        styles["Normal"],
    ))
    story.append(Paragraph(
        f"<b>Valor total autorizado:</b> {valor_fmt} (canceladas não entram na soma)",
        styles["Normal"],
    ))
    story.append(Spacer(1, 14))

    # Tabela — só se tiver nota
    if notas:
        headers = ["#", "Modelo", "Nº", "Série", "Emissão", "Status", "Valor"]
        rows = [headers]
        for i, n in enumerate(sorted(notas, key=lambda x: (x.criado_em or datetime.min)), 1):
            modelo = "NFC-e" if _modelo_da_nota(n) == 65 else "NF-e"
            emissao = n.criado_em.strftime("%d/%m/%Y %H:%M") if n.criado_em else "-"
            val = f"R$ {float(n.valor_total or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            rows.append([
                str(i),
                modelo,
                str(n.numero or "-"),
                str(n.serie or "-"),
                emissao,
                (n.status or "-").capitalize(),
                val,
            ])
        table = Table(rows, repeatRows=1, colWidths=[8*mm, 18*mm, 18*mm, 14*mm, 34*mm, 26*mm, 30*mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("<i>Nenhuma nota no período.</i>", styles["Italic"]))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Empacotador principal
# ---------------------------------------------------------------------------


async def preparar_lote(
    empresa: Empresa,
    notas: list[Nota],
    inicio: datetime,
    fim: datetime,
    *,
    incluir: str = "ambos",  # xml | pdf | ambos
    acbr_service: Optional[ACBrAPIService] = None,
) -> LoteExportado:
    """Baixa XMLs/PDFs da ACBr, empacota em ZIP por pasta + gera PDF relatório.

    Filtra `notas` por status válido (autorizada/cancelada). Notas rejeitadas/
    pendentes/rascunho são ignoradas silenciosamente (não têm documento fiscal
    pra empacotar).
    """
    acbr = acbr_service or ACBrAPIService()
    # `set` pra evitar duplicata caso duas rotas empacotem a mesma nota
    notas_com_doc = [n for n in notas if n.status in ("autorizada", "cancelada")]
    resumo = resumir(empresa, notas_com_doc, inicio, fim)
    falhas: list[str] = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Relatório PDF primeiro pra aparecer no topo do ZIP quando aberto
        try:
            pdf_bytes = _gerar_relatorio_pdf(resumo, notas_com_doc)
            zf.writestr("RELATORIO.pdf", pdf_bytes)
        except Exception as exc:  # relatório é bônus — não travar export
            falhas.append(f"RELATORIO.pdf: falha ao gerar — {exc}")

        for n in notas_com_doc:
            pasta = _pasta_da_nota(n)
            chave = n.chave_acesso or f"NOTA_SEM_CHAVE_{n.id}"
            num = n.numero or n.id
            ser = n.serie or 1
            base = f"{pasta}/{chave}_n{num}_s{ser}"

            if not n.acbr_id:
                falhas.append(f"{base}: sem acbr_id — nota não foi emitida via ACBr")
                continue

            modelo = _modelo_da_nota(n)

            if incluir in ("xml", "ambos"):
                ok, data = await acbr.baixar_xml(n.acbr_id, modelo=modelo)
                if ok:
                    zf.writestr(f"{base}.xml", data)
                else:
                    falhas.append(f"{base}.xml: ACBr rejeitou — {data}")

            if incluir in ("pdf", "ambos"):
                ok, data = await acbr.baixar_pdf(n.acbr_id, modelo=modelo)
                if ok:
                    zf.writestr(f"{base}.pdf", data)
                else:
                    falhas.append(f"{base}.pdf: ACBr rejeitou — {data}")

        if falhas:
            zf.writestr("RELATORIO_FALHAS.txt", "\n".join(falhas).encode("utf-8"))

    filename = (
        f"notas_{empresa.cnpj}_"
        f"{inicio.strftime('%Y-%m-%d')}_a_{fim.strftime('%Y-%m-%d')}.zip"
    )
    return LoteExportado(
        zip_bytes=buf.getvalue(),
        filename=filename,
        resumo=resumo,
        falhas=falhas,
    )
