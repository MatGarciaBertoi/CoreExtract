"""
CoreExtract — Motor Inteligente de Extração e Resumo de Currículos
Servidor FastAPI — sem custos, roda localmente ou em qualquer VPS.

Iniciar:
  python main.py
  ou
  uvicorn main:app --reload --host 0.0.0.0 --port 8080

Endpoints:
  GET  /          → Frontend HTML (interface de upload)
  GET  /health    → Health check
  POST /extract   → Processa arquivo(s), retorna JSON e opcionalmente envia e-mail
  GET  /settings  → Retorna configurações atuais (senha mascarada)
  POST /settings  → Salva configurações no .env em tempo real
"""
from __future__ import annotations

import hashlib
import importlib
import io
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import config
import settings_db
from ai_processor import analyze_resume
from email_builder import build_email_content
from excel_exporter import generate_excel_report
from extractors import extract_text
from mailer import send_email
from models import EmailRequest, ProcessingResult, ResumeOutput
from utils.logger import get_logger
from utils.request_context import RequestContext

logger = get_logger("main")

# =========================================================================== #
#  APP                                                                          #
# =========================================================================== #

app = FastAPI(
    title="CoreExtract",
    description="Motor Inteligente de Extração e Resumo de Currículos",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

from utils.paths import FRONTEND_PATH as _FRONTEND, ENV_PATH as _ENV_PATH


# =========================================================================== #
#  HELPERS — leitura e escrita do .env em tempo real                            #
# =========================================================================== #

def _read_env_dict() -> dict[str, str]:
    """Lê o .env e retorna um dicionário {chave: valor}."""
    result: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    """Atualiza (ou adiciona) uma chave no .env sem perder as outras."""
    text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    _ENV_PATH.write_text(text, encoding="utf-8")


class SettingsPayload(BaseModel):
    # Credenciais Gmail
    gmail_user:           Optional[str] = None
    gmail_app_password:   Optional[str] = None
    # Credenciais Outlook (armazenadas separadamente)
    outlook_user:         Optional[str] = None
    outlook_app_password: Optional[str] = None
    # Compartilhados
    email_from_name:      Optional[str] = None
    gemini_model:         Optional[str] = None
    email_provider:       Optional[str] = None   # "gmail" | "outlook"


class CommentPayload(BaseModel):
    filename: str
    comment: str


class ExcelExportPayload(BaseModel):
    results:             list[dict]
    tema:                Optional[str] = "Triagem Geral"
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None


class EmailSendPayload(BaseModel):
    results:             list[dict]
    destinatario:        str
    destinatario_nome:   Optional[str] = None   # nome legível p/ saudação no e-mail
    cc:                  Optional[str] = None   # e-mails em cópia, separados por vírgula
    tema:                Optional[str] = "Triagem Geral"
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None
    contexto_adicional:  Optional[str] = None


# =========================================================================== #
#  MIDDLEWARE — request ID em todas as respostas                                #
# =========================================================================== #

@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or hashlib.md5(
        f"{time.time()}".encode()
    ).hexdigest()[:12]
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# =========================================================================== #
#  UTILITÁRIO — processa um único arquivo                                       #
# =========================================================================== #

def _process_one(
    file_bytes: bytes,
    filename: str,
    job_description: Optional[str],
    request_id: str,
) -> ProcessingResult:
    ctx = RequestContext(request_id=request_id, filename=filename)
    ctx.file_size_bytes = len(file_bytes)
    ctx.compute_file_hash(file_bytes)

    try:
        ctx.step("validate")
        ext = Path(filename).suffix.lower()
        if ext not in config.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Formato '{ext}' não suportado. "
                f"Aceitos: {sorted(config.SUPPORTED_EXTENSIONS)}"
            )
        max_bytes = config.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise ValueError(
                f"Arquivo excede {config.MAX_FILE_SIZE_MB} MB "
                f"({len(file_bytes) / 1024 / 1024:.1f} MB recebidos)."
            )

        ctx.step("extract")
        raw_text = extract_text(file_bytes, filename)

        resume: ResumeOutput = analyze_resume(
            raw_text=raw_text,
            ctx=ctx,
            job_description=job_description,
        )

        ctx.step("done")
        logger.info(
            "Processado: '%s' | score=%d elapsed=%dms",
            filename, resume.scores.score_geral, ctx.elapsed_ms,
            extra=ctx.to_log_extras(),
        )
        return ProcessingResult(
            filename=filename, status="ok",
            resume=resume, meta=ctx.to_response_meta(),
        )

    except Exception as exc:
        ctx.step(f"error:{type(exc).__name__}")
        logger.warning("Falha em '%s': %s", filename, str(exc)[:200], extra=ctx.to_log_extras())
        return ProcessingResult(
            filename=filename, status="error",
            error=str(exc), meta=ctx.to_response_meta(),
        )


# =========================================================================== #
#  ROTAS                                                                        #
# =========================================================================== #

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def frontend():
    """Serve a interface de upload."""
    if _FRONTEND.exists():
        return HTMLResponse(_FRONTEND.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>CoreExtract API</h1><p>Use POST /extract</p>")


@app.get("/health")
async def health():
    """Health check — usado por monitores e load balancers."""
    return {
        "status":  "healthy",
        "service": "coreextract",
        "model":   config.GEMINI_MODEL,
        "limits": {
            "max_files":   config.MAX_FILES_PER_REQUEST,
            "max_file_mb": config.MAX_FILE_SIZE_MB,
            "formats":     sorted(config.SUPPORTED_EXTENSIONS),
        },
    }


@app.get("/settings")
async def get_settings():
    """Retorna as configurações atuais — senha mascarada."""
    db = settings_db.get_all()
    user = db.get("GMAIL_USER", "")
    pwd  = db.get("GMAIL_APP_PASSWORD", "")
    out_user = db.get("OUTLOOK_USER", "")
    out_pwd  = db.get("OUTLOOK_APP_PASSWORD", "")
    return {
        # Gmail
        "gmail_user":         user,
        "gmail_app_password": "__SAVED__" if pwd else "",
        "gmail_configured":   bool(user and pwd),
        # Outlook
        "outlook_user":         out_user,
        "outlook_app_password": "__SAVED__" if out_pwd else "",
        "outlook_configured":   bool(out_user and out_pwd),
        # Compartilhados
        "email_from_name":    db.get("EMAIL_FROM_NAME", "CoreExtract · RH Inteligente"),
        "gemini_model":       db.get("GEMINI_MODEL", config.GEMINI_MODEL),
        "email_provider":     db.get("EMAIL_PROVIDER", "gmail"),
        # Chave Gemini gerenciada pelo distribuidor (oculta campo na UI)
        "gemini_managed":     config.GEMINI_MANAGED,
        "gemini_configured":  bool(config.GEMINI_API_KEY),
    }


@app.post("/settings")
async def save_settings(payload: SettingsPayload):
    """
    Salva configurações no SQLite e recarrega o módulo config em memória.
    Apenas campos não-nulos e não-vazios são atualizados.
    A senha não é alterada se o valor for '__SAVED__' ou contiver apenas '•'.
    """
    import ai_processor  # imported here to update _model when gemini_model changes

    to_save: dict[str, str] = {}
    updated: list[str] = []
    old_model = settings_db.get("GEMINI_MODEL", config.GEMINI_MODEL)

    # ── Credenciais Gmail ──
    if payload.gmail_user is not None:
        to_save["GMAIL_USER"] = payload.gmail_user.strip()
        updated.append("GMAIL_USER")
    pwd_gmail = payload.gmail_app_password or ""
    if pwd_gmail and pwd_gmail != "__SAVED__" and pwd_gmail.strip("•").strip():
        to_save["GMAIL_APP_PASSWORD"] = pwd_gmail.strip()
        updated.append("GMAIL_APP_PASSWORD")

    # ── Credenciais Outlook (armazenadas separadamente) ──
    if payload.outlook_user is not None:
        to_save["OUTLOOK_USER"] = payload.outlook_user.strip()
        updated.append("OUTLOOK_USER")
    pwd_out = payload.outlook_app_password or ""
    if pwd_out and pwd_out != "__SAVED__" and pwd_out.strip("•").strip():
        to_save["OUTLOOK_APP_PASSWORD"] = pwd_out.strip()
        updated.append("OUTLOOK_APP_PASSWORD")

    if payload.email_from_name is not None:
        to_save["EMAIL_FROM_NAME"] = payload.email_from_name.strip()
        updated.append("EMAIL_FROM_NAME")

    if payload.gemini_model and payload.gemini_model.strip():
        to_save["GEMINI_MODEL"] = payload.gemini_model.strip()
        updated.append("GEMINI_MODEL")

    if payload.email_provider and payload.email_provider.strip() in ("gmail", "outlook"):
        to_save["EMAIL_PROVIDER"] = payload.email_provider.strip()
        updated.append("EMAIL_PROVIDER")

    if to_save:
        settings_db.set_many(to_save)

    # Recarrega config em memória para que a mudança valha imediatamente
    importlib.reload(config)

    # Update the live Gemini model instance if the model name changed
    new_model = to_save.get("GEMINI_MODEL", old_model)
    if new_model and new_model != old_model:
        import google.generativeai as genai
        ai_processor._model = genai.GenerativeModel(new_model)
        logger.info("Modelo Gemini atualizado para: %s", new_model)

    db_after = settings_db.get_all()
    logger.info("Configurações atualizadas: %s", updated)
    return {"saved": updated, "gmail_configured": bool(
        db_after.get("GMAIL_USER") and db_after.get("GMAIL_APP_PASSWORD")
    )}


@app.post("/settings/test-email")
async def test_email(payload: SettingsPayload):
    """Testa o envio de e-mail com as credenciais do provedor selecionado."""
    provider = (payload.email_provider or settings_db.get("EMAIL_PROVIDER") or "gmail").strip()

    if provider == "outlook":
        raw_user = (payload.outlook_user or "").strip()
        test_user = raw_user or settings_db.get("OUTLOOK_USER", "")
        raw_pwd   = (payload.outlook_app_password or "").strip()
        db_pwd_key = "OUTLOOK_APP_PASSWORD"
    else:
        raw_user = (payload.gmail_user or "").strip()
        test_user = raw_user or settings_db.get("GMAIL_USER", "")
        raw_pwd   = (payload.gmail_app_password or "").strip()
        db_pwd_key = "GMAIL_APP_PASSWORD"

    if not raw_pwd or raw_pwd == "__SAVED__" or not raw_pwd.strip("•").strip():
        test_pwd = settings_db.get(db_pwd_key, "")
    else:
        test_pwd = raw_pwd

    if not test_user or not test_pwd:
        raise HTTPException(400, "Informe usuário e senha antes de testar.")

    try:
        import smtplib
        import ssl
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from_name = settings_db.get("EMAIL_FROM_NAME", config.EMAIL_FROM_NAME)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "CoreExtract — Teste de configuração ✓"
        msg["From"]    = f"{from_name} <{test_user}>"
        msg["To"]      = test_user
        html_body = (
            "<p>Olá! Se você recebeu este e-mail, o CoreExtract está configurado "
            "corretamente para enviar relatórios de triagem.</p>"
            "<p><b>CoreExtract · RH Inteligente</b></p>"
        )
        msg.attach(MIMEText("Este e-mail requer um cliente que suporte HTML.", "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        _SMTP_MAP = {"gmail": "smtp.gmail.com", "outlook": "smtp.office365.com"}
        provider  = (payload.email_provider or settings_db.get("EMAIL_PROVIDER") or "gmail")
        smtp_host = _SMTP_MAP.get(provider, "smtp.gmail.com")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(test_user, test_pwd)
            server.sendmail(test_user, test_user, msg.as_string())

        return {"success": True, "detail": {"status": "sent", "to": test_user}}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/extract")
async def extract(
    request: Request,
    files: Annotated[list[UploadFile], File(description="Arquivos de currículo (PDF, DOCX, XLSX, TXT)")],
    # Análise de fit opcional
    job_description: Annotated[Optional[str], Form()] = None,
    # Parâmetros de e-mail (todos opcionais)
    send_email_flag: Annotated[Optional[str], Form(alias="send_email")] = None,
    destinatario:    Annotated[Optional[str], Form()] = None,
    tema:            Annotated[Optional[str], Form()] = None,
    nome_recrutador: Annotated[Optional[str], Form()] = None,
    empresa_recrutadora: Annotated[Optional[str], Form()] = None,
    contexto_adicional:  Annotated[Optional[str], Form()] = None,
):
    """
    Processa um ou mais arquivos de currículo.

    - Retorna JSON estruturado para cada arquivo.
    - Se `send_email=true` e `destinatario` informado, envia e-mail de triagem.
    - Se `job_description` informado, calcula score de fit para cada candidato.
    """
    req_id = request.state.request_id

    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    if len(files) > config.MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {config.MAX_FILES_PER_REQUEST} arquivos por requisição."
        )

    if not config.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY não configurada. Adicione no arquivo .env."
        )

    t_start = time.monotonic()

    # Limpa comentários anteriores para estes arquivos — cada análise começa zerada
    uploaded_names = [f.filename for f in files if f.filename]
    if uploaded_names:
        settings_db.delete_comments_for_files(uploaded_names)

    # Processa todos os arquivos
    results: list[ProcessingResult] = []
    for uploaded in files:
        content = await uploaded.read()
        result  = _process_one(
            file_bytes=content,
            filename=uploaded.filename or "arquivo",
            job_description=job_description or None,
            request_id=req_id,
        )
        results.append(result)

    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    n_ok  = sum(1 for r in results if r.status == "ok")
    n_err = sum(1 for r in results if r.status == "error")

    response_body: dict = {
        "request_id":       req_id,
        "total":            len(results),
        "success":          n_ok,
        "errors":           n_err,
        "total_elapsed_ms": elapsed_ms,
        "results":          [r.model_dump() for r in results],
        "email_sent":       False,
    }

    # Envio de e-mail (opcional)
    if send_email_flag and send_email_flag.lower() == "true":
        if not destinatario:
            response_body["email_error"] = "Campo 'destinatario' é obrigatório para envio de e-mail."
        else:
            try:
                dest_nome = (
                    destinatario.split("@")[0]
                    .replace(".", " ").replace("_", " ").title()
                )
                email_content = build_email_content(
                    results=results,
                    tema=tema or "Triagem Geral",
                    destinatario_nome=dest_nome,
                    nome_recrutador=nome_recrutador,
                    empresa_recrutadora=empresa_recrutadora,
                    contexto_adicional=contexto_adicional,
                )

                # Gera o relatório Excel para anexar ao e-mail
                results_dicts = [r.model_dump() for r in results]
                xlsx_bytes = generate_excel_report(
                    results=results_dicts,
                    tema=tema or "Triagem Geral",
                    nome_recrutador=nome_recrutador,
                    empresa_recrutadora=empresa_recrutadora,
                )
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                attachments = [
                    {
                        "filename": f"CoreExtract_Triagem_{ts}.xlsx",
                        "data":     xlsx_bytes,
                        "mimetype": (
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        ),
                    }
                ]

                mail_result = send_email(
                    to_email=destinatario,
                    subject=email_content["subject"],
                    html_body=email_content["html_body"],
                    attachments=attachments,
                )
                response_body["email_sent"]    = True
                response_body["email_status"]  = mail_result
                response_body["email_subject"] = email_content["subject"]

                logger.info("E-mail enviado para %s (com anexo Excel)", destinatario,
                            extra={"ce_request_id": req_id})

            except Exception as exc:
                logger.error("Falha ao enviar e-mail: %s", exc,
                             extra={"ce_request_id": req_id})
                response_body["email_error"] = str(exc)

    logger.info(
        "Requisição finalizada | ok=%d err=%d elapsed=%dms email=%s",
        n_ok, n_err, elapsed_ms, response_body["email_sent"],
        extra={"ce_request_id": req_id},
    )

    return JSONResponse(content=response_body)


@app.post("/email/send")
async def send_triagem_email(payload: EmailSendPayload):
    """
    Envia o e-mail de triagem com o relatório Excel anexado.
    Recebe os resultados já processados como JSON — não reprocessa arquivos.
    """
    if not payload.results:
        raise HTTPException(status_code=400, detail="Lista de resultados vazia.")
    if not payload.destinatario:
        raise HTTPException(status_code=400, detail="Campo 'destinatario' é obrigatório.")

    try:
        from models import ProcessingResult as PR
        pr_results = []
        for r in payload.results:
            if not isinstance(r, dict):
                continue
            try:
                pr_results.append(PR.model_validate(r))
            except Exception as ve:
                fname = r.get("filename", "arquivo")
                logger.warning(
                    "Validação parcial ignorada para '%s': %s", fname, ve
                )
                # Cria resultado mínimo de erro para manter o arquivo no e-mail
                pr_results.append(
                    PR(filename=fname, status="error",
                       error=f"Dados incompletos: {str(ve)[:120]}")
                )

        if not pr_results:
            raise HTTPException(status_code=400, detail="Nenhum resultado válido na lista.")

        # Usa nome explícito se informado; caso contrário, deriva do e-mail
        dest_nome = payload.destinatario_nome or (
            payload.destinatario.split("@")[0]
            .replace(".", " ").replace("_", " ").title()
        )

        # Busca anotações do recrutador salvas no SQLite para cada arquivo
        filenames = [r.filename for r in pr_results]
        recruiter_comments = settings_db.get_comments_for_files(filenames)

        email_content = build_email_content(
            results=pr_results,
            tema=payload.tema or "Triagem Geral",
            destinatario_nome=dest_nome,
            nome_recrutador=payload.nome_recrutador,
            empresa_recrutadora=payload.empresa_recrutadora,
            contexto_adicional=payload.contexto_adicional,
            recruiter_comments=recruiter_comments,
        )

        xlsx_bytes = generate_excel_report(
            results=payload.results,
            tema=payload.tema or "Triagem Geral",
            nome_recrutador=payload.nome_recrutador,
            empresa_recrutadora=payload.empresa_recrutadora,
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        attachments = [
            {
                "filename": f"CoreExtract_Triagem_{ts}.xlsx",
                "data":     xlsx_bytes,
                "mimetype": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            }
        ]

        mail_result = send_email(
            to_email=payload.destinatario,
            subject=email_content["subject"],
            html_body=email_content["html_body"],
            attachments=attachments,
            cc=payload.cc or None,
        )

        logger.info("E-mail de triagem enviado para %s", payload.destinatario)
        return {"sent": True, "status": mail_result, "subject": email_content["subject"]}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao enviar e-mail de triagem: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/export/excel")
async def export_excel(payload: ExcelExportPayload):
    """
    Gera e retorna um relatório Excel (.xlsx) com gráficos a partir dos resultados.
    """
    if not payload.results:
        raise HTTPException(status_code=400, detail="Lista de resultados vazia.")

    try:
        xlsx_bytes = generate_excel_report(
            results=payload.results,
            tema=payload.tema or "Triagem Geral",
            nome_recrutador=payload.nome_recrutador,
            empresa_recrutadora=payload.empresa_recrutadora,
        )
        ts       = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"CoreExtract_Triagem_{ts}.xlsx"

        return StreamingResponse(
            io.BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao gerar Excel: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/comments")
async def get_comments(filenames: str = ""):
    """Return comments for a comma-separated list of filenames."""
    if not filenames:
        return JSONResponse(content={})
    names = [f.strip() for f in filenames.split(",") if f.strip()]
    return JSONResponse(content=settings_db.get_comments_for_files(names))


@app.post("/comments")
async def save_comment(payload: CommentPayload):
    """Save or update a recruiter comment for a file."""
    settings_db.save_comment(payload.filename, payload.comment)
    return JSONResponse(content={"ok": True})


# =========================================================================== #
#  INICIALIZAÇÃO DIRETA                                                         #
# =========================================================================== #

if __name__ == "__main__":
    from utils.paths import is_frozen
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=not is_frozen(),   # reload=False no executável distribuído
        log_level="info",
    )
