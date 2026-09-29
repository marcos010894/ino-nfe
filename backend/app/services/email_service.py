"""Envio de e-mail via SMTP (Hostinger padrão) — Central de Documentos v3.

Uso primário: mandar ZIP com XMLs+PDFs+relatório pro contador (manual pelo
botão "Enviar ao contador" ou pelo cron mensal dia N).

Config vem de `app.core.config.settings` (SMTP_HOST/PORT/USER/PASSWORD).
Se `smtp_host` estiver vazio, `enviar_email()` levanta RuntimeError — força
o operador a configurar env var no VPS antes de ativar o envio.
"""
from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable, Optional, Sequence

from app.core.config import settings


class EmailAttachment:
    """Anexo pronto pra ir no MIME. Não faz IO — bytes vêm de quem chama."""

    def __init__(self, filename: str, content: bytes, content_type: Optional[str] = None):
        self.filename = filename
        self.content = content
        # Fallback: adivinha pelo nome. Se falhar cai em octet-stream.
        if content_type is None:
            guess, _ = mimetypes.guess_type(filename)
            content_type = guess or "application/octet-stream"
        self.content_type = content_type


def _split_addrs(raw: Optional[str]) -> list[str]:
    """Aceita string separada por vírgula/ponto-e-vírgula e devolve lista limpa."""
    if not raw:
        return []
    out: list[str] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(part)
    return out


def enviar_email(
    *,
    to: str | Sequence[str],
    subject: str,
    body_text: str,
    cc: str | Sequence[str] | None = None,
    reply_to: Optional[str] = None,
    attachments: Iterable[EmailAttachment] = (),
    body_html: Optional[str] = None,
) -> None:
    """Envia e-mail via SMTP_SSL síncrono. Levanta em falha.

    Não retorna nada — quem chama trata exceção (o log em `EnvioContadorLog`
    grava `ok=False` + `erro=str(exc)`).
    """
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError(
            "SMTP não configurado — defina SMTP_HOST, SMTP_USER, SMTP_PASSWORD no ambiente."
        )

    to_list = _split_addrs(to) if isinstance(to, str) else [t.strip() for t in to if t.strip()]
    cc_list = _split_addrs(cc) if isinstance(cc, str) else (
        [c.strip() for c in cc if c and c.strip()] if cc else []
    )
    if not to_list:
        raise ValueError("enviar_email exige pelo menos 1 destinatário em `to`.")

    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_user))
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    for att in attachments:
        maintype, _, subtype = att.content_type.partition("/")
        if not subtype:
            subtype = "octet-stream"
        msg.add_attachment(att.content, maintype=maintype, subtype=subtype, filename=att.filename)

    # Hostinger recomenda porta 465 SSL. Se ficar 587 STARTTLS um dia,
    # trocar por smtplib.SMTP + starttls().
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=60) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg, to_addrs=to_list + cc_list)


# ---------------------------------------------------------------------------
# Templates de mensagem pro contador
# ---------------------------------------------------------------------------

ASSUNTO_PADRAO = "XMLs {empresa} · {periodo}"
MENSAGEM_PADRAO = (
    "Olá, {contador}!\n\n"
    "Segue em anexo o lote de XMLs e o relatório fiscal da {empresa} referente a {periodo}.\n\n"
    "Qualquer dúvida, é só responder este e-mail."
)


def aplicar_template(texto: Optional[str], *, contador: str, empresa: str, periodo: str, fallback: str) -> str:
    """Substitui os placeholders {contador} {empresa} {periodo} no texto.

    Usa `fallback` quando `texto` é None/vazio — permite deixar a empresa sem
    override e ainda ter mensagem decente. `str.format` seria arriscado
    (KeyError se aparecer `{outra}`), então substituição manual.
    """
    base = (texto or fallback)
    return (
        base.replace("{contador}", contador or "contador")
        .replace("{empresa}", empresa)
        .replace("{periodo}", periodo)
    )
