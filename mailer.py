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
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
import settings_db
from utils.logger import get_logger

logger = get_logger("mailer")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def send_email(to_email: str, subject: str, html_body: str) -> dict:
    """
    Envia o e-mail via Gmail SMTP com TLS.

    Credentials are read from settings_db at call time so that changes made
    via the /settings endpoint take effect immediately without a server restart.

    Returns:
        dict com "status" e "to".

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

    # Monta a mensagem
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{gmail_user}>"
    msg["To"]      = to_email

    # Parte HTML (principal) + fallback texto puro
    plain_fallback = "Este e-mail requer um cliente que suporte HTML."
    msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,      "html",  "utf-8"))

    context = ssl.create_default_context()

    logger.info("Enviando e-mail para %s | assunto: '%s'", to_email, subject)

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_email, msg.as_string())

    logger.info("E-mail enviado com sucesso para %s", to_email)
    return {"status": "sent", "to": to_email}
