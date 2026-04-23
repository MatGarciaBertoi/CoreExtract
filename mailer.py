"""
Envio de e-mail via Gmail SMTP — 100% gratuito.

Pré-requisito (uma única vez):
  1. Acesse myaccount.google.com → Segurança → Verificação em duas etapas (ativar)
  2. Acesse myaccount.google.com → Segurança → Senhas de app
  3. Gere uma senha de app para "Outro (nome personalizado)" → "CoreExtract"
  4. Coloque a senha gerada em GMAIL_APP_PASSWORD no .env

A senha de app é diferente da sua senha normal do Gmail.
"""
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import config
import settings_db
from utils.logger import get_logger

logger = get_logger("mailer")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Optional[list[dict]] = None,
) -> dict:
    """
    Envia o e-mail via Gmail SMTP com TLS.

    Credentials are read from settings_db at call time so that changes made
    via the /settings endpoint take effect immediately without a server restart.

    Args:
        to_email:    Destinatário.
        subject:     Assunto do e-mail.
        html_body:   Corpo HTML.
        attachments: Lista opcional de dicts com chaves:
                       - filename (str)  — nome do arquivo anexo
                       - data    (bytes) — conteúdo binário
                       - mimetype (str)  — ex: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    Returns:
        dict com "status", "to" e "attachments" (número de anexos).

    Raises:
        ValueError: se GMAIL_USER ou GMAIL_APP_PASSWORD não estiverem configurados.
        smtplib.SMTPException: em caso de falha no envio.
    """
    # Read credentials at call time (not from module-level config) so live
    # settings changes are respected immediately.
    gmail_user     = settings_db.get("GMAIL_USER") or config.GMAIL_USER
    gmail_password = settings_db.get("GMAIL_APP_PASSWORD") or config.GMAIL_APP_PASSWORD
    from_name      = settings_db.get("EMAIL_FROM_NAME") or config.EMAIL_FROM_NAME

    if not gmail_user or not gmail_password:
        raise ValueError(
            "GMAIL_USER e GMAIL_APP_PASSWORD precisam estar configurados nas Configurações. "
            "Veja as instruções no topo de mailer.py."
        )

    has_attachments = bool(attachments)

    # Outer container: "mixed" when there are attachments, "alternative" otherwise
    msg = MIMEMultipart("mixed" if has_attachments else "alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{gmail_user}>"
    msg["To"]      = to_email

    # HTML + plain-text block (always wrapped in "alternative" when there are attachments)
    plain_fallback = "Este e-mail requer um cliente que suporte HTML."
    if has_attachments:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_fallback, "plain", "utf-8"))
        alt.attach(MIMEText(html_body,      "html",  "utf-8"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,      "html",  "utf-8"))

    # Attach files
    n_attachments = 0
    if has_attachments:
        for att in attachments:
            filename = att.get("filename", "attachment")
            data     = att.get("data", b"")
            mimetype = att.get("mimetype", "application/octet-stream")
            main_type, _, sub_type = mimetype.partition("/")

            part = MIMEBase(main_type, sub_type)
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename,
            )
            msg.attach(part)
            n_attachments += 1
            logger.info("Anexo adicionado: %s (%d bytes)", filename, len(data))

    context = ssl.create_default_context()

    logger.info(
        "Enviando e-mail para %s | assunto: '%s' | anexos: %d",
        to_email, subject, n_attachments,
    )

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_email, msg.as_string())

    logger.info("E-mail enviado com sucesso para %s", to_email)
    return {"status": "sent", "to": to_email, "attachments": n_attachments}
