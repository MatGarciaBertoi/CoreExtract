"""
BTExtract — Motor Inteligente de Extração e Resumo de Currículos
Servidor FastAPI — multi-tenant com autenticação JWT.

Iniciar:
  python main.py
  ou
  uvicorn main:app --reload --host 0.0.0.0 --port 8080

Roles:
  superadmin  → dono do sistema; acessa /admin
  admin       → admin de empresa; acessa /empresa/*
  user        → colaborador; acessa a aplicação principal

Endpoints públicos  (sem JWT):
  GET  /               → frontend.html (app principal)
  GET  /login          → login.html
  GET  /health         → health check
  POST /auth/login     → autentica e retorna JWT

Endpoints protegidos (exigem JWT — header Authorization: Bearer <token>):
  GET  /auth/me                     → dados do usuário autenticado
  POST /auth/alterar-senha          → altera senha do próprio usuário
  POST /extract                     → processa currículos
  POST /export/excel                → gera Excel
  POST /email/send                  → envia e-mail de triagem
  GET|POST /comments                → comentários de candidatos
  GET|POST /settings                → configurações (admin+)
  POST /settings/test-email         → testa SMTP (admin+)

  [admin/superadmin]
  GET  /admin                       → admin.html (painel superadmin)
  GET  /admin/empresas              → lista empresas
  POST /admin/empresas              → cria empresa + admin
  DELETE /admin/empresas/{id}       → desativa empresa
  GET  /admin/audit                 → audit log global

  [admin da empresa]
  GET  /empresa/usuarios            → lista usuários da empresa
  POST /empresa/usuarios            → cria usuário na empresa
  DELETE /empresa/usuarios/{id}     → desativa usuário

  [LGPD]
  DELETE /lgpd/apagar-minha-conta  → anonimiza PII do usuário logado
"""
from __future__ import annotations

import hashlib
import importlib
import io
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import auth_db
import config
import settings_db
from ai_processor import analyze_resume
from auth import get_current_user, require_admin, require_superadmin
from email_builder import build_email_content
from excel_exporter import generate_excel_report
from extractors import extract_text
from mailer import send_email
from models import (
    AlterarSenhaPayload,
    EmailRequest,
    EmpresaCreate,
    EmpresaResponse,
    LoginPayload,
    ProcessingResult,
    ResumeOutput,
    Token,
    UserCreate,
    UserResponse,
)
from utils.logger import get_logger
from utils.paths import (
    ENV_PATH as _ENV_PATH,
    FRONTEND_PATH as _FRONTEND,
    SESSION_PATH as _SESSION_PATH,
    get_resource,
)
from utils.request_context import RequestContext

logger = get_logger("main")


# =========================================================================== #
#  LIFESPAN — startup / shutdown                                                #
# =========================================================================== #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("BTExtract inicializando...")
    auth.bootstrap_superadmin()
    logger.info("Bootstrap superadmin concluido.")
    yield
    # ── Shutdown ──
    logger.info("BTExtract encerrando.")


# =========================================================================== #
#  APP                                                                          #
# =========================================================================== #

app = FastAPI(
    title="BTExtract",
    description="Motor Inteligente de Extração e Resumo de Currículos",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

_static_dir = get_resource("static")
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# =========================================================================== #
#  HELPERS — .env                                                               #
# =========================================================================== #

def _read_env_dict() -> dict[str, str]:
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
    text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    _ENV_PATH.write_text(text, encoding="utf-8")


# =========================================================================== #
#  PAYLOADS INTERNOS                                                            #
# =========================================================================== #

class SettingsPayload(BaseModel):
    gmail_user:           Optional[str] = None
    gmail_app_password:   Optional[str] = None
    outlook_user:         Optional[str] = None
    outlook_app_password: Optional[str] = None
    email_from_name:      Optional[str] = None
    gemini_model:         Optional[str] = None
    email_provider:       Optional[str] = None


class CommentPayload(BaseModel):
    filename: str
    comment:  str


class SalvarSessaoPayload(BaseModel):
    results:  list[dict]
    tema:     Optional[str] = "Triagem Geral"


class ExcelExportPayload(BaseModel):
    results:             list[dict]
    tema:                Optional[str] = "Triagem Geral"
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None


class EmailSendPayload(BaseModel):
    results:             list[dict]
    destinatario:        str
    destinatario_nome:   Optional[str] = None
    cc:                  Optional[str] = None
    tema:                Optional[str] = "Triagem Geral"
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None
    contexto_adicional:  Optional[str] = None
    incluir_excel:       bool = True


# =========================================================================== #
#  MIDDLEWARE — request ID                                                      #
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
#  HELPER — processa um arquivo                                                 #
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
        if len(file_bytes) > config.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(
                f"Arquivo excede {config.MAX_FILE_SIZE_MB} MB "
                f"({len(file_bytes) / 1024 / 1024:.1f} MB recebidos)."
            )
        ctx.step("extract")
        raw_text = extract_text(file_bytes, filename)
        resume: ResumeOutput = analyze_resume(
            raw_text=raw_text, ctx=ctx, job_description=job_description,
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
#  ROTAS PÚBLICAS                                                               #
# =========================================================================== #

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def frontend():
    """Serve o frontend principal (autenticação verificada via JS)."""
    if _FRONTEND.exists():
        return HTMLResponse(_FRONTEND.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>BTExtract API</h1><p>Use POST /extract</p>")


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page():
    """Serve a página de login."""
    login_path = get_resource("templates/login.html")
    if login_path.exists():
        return HTMLResponse(login_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Login — BTExtract</h1>")


@app.get("/politica-de-privacidade", response_class=HTMLResponse, include_in_schema=False)
async def privacy_page():
    """Página pública de Política de Privacidade (LGPD)."""
    path = get_resource("templates/privacidade.html")
    if path.exists():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Política de Privacidade — BTExtract</h1>")


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    """Serve o painel de superadmin (acesso verificado via JS + JWT)."""
    admin_path = get_resource("templates/admin.html")
    if admin_path.exists():
        return HTMLResponse(admin_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Admin — BTExtract</h1>")


@app.get("/health")
async def health():
    return {
        "status":  "healthy",
        "service": "btextract",
        "model":   config.GEMINI_MODEL,
        "limits": {
            "max_files":   config.MAX_FILES_PER_REQUEST,
            "max_file_mb": config.MAX_FILE_SIZE_MB,
            "formats":     sorted(config.SUPPORTED_EXTENSIONS),
        },
    }


# =========================================================================== #
#  ROTAS DE AUTENTICAÇÃO                                                        #
# =========================================================================== #

@app.post("/auth/login", response_model=Token, tags=["auth"])
async def login(payload: LoginPayload, request: Request):
    """
    Autentica um usuário e retorna um JWT.
    Corpo: { "email": "...", "senha": "..." }
    """
    user = auth_db.get_usuario_por_email(payload.email)
    if not user or not auth.verify_password(payload.senha, user["senha_hash"]):
        auth_db.log_acao(
            "login_falha",
            detalhes=f"email={payload.email}",
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha incorretos.",
        )

    empresa = auth_db.get_empresa(user["empresa_id"])
    if empresa and not empresa.get("ativo"):
        raise HTTPException(status_code=403, detail="Empresa inativa. Entre em contato com o suporte.")

    token = auth.create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=user["role"],
        empresa_id=user["empresa_id"],
        nome=user["nome"],
    )

    auth_db.log_acao(
        "login_ok",
        usuario_id=user["id"],
        empresa_id=user["empresa_id"],
        ip=request.client.host if request.client else None,
    )

    return Token(
        access_token=token,
        role=user["role"],
        nome=user["nome"],
        empresa_id=user["empresa_id"],
        empresa_nome=empresa["razao_social"] if empresa else None,
    )


@app.get("/auth/me", tags=["auth"])
async def me(current_user: dict = Depends(get_current_user)):
    """Retorna dados do usuário autenticado."""
    user = auth_db.get_usuario(current_user["sub"])
    empresa = auth_db.get_empresa(current_user["empresa_id"])
    return {
        "id":          current_user["sub"],
        "email":       current_user["email"],
        "nome":        current_user.get("nome", ""),
        "role":        current_user["role"],
        "empresa_id":  current_user["empresa_id"],
        "empresa_nome": empresa["razao_social"] if empresa else None,
    }


@app.post("/auth/alterar-senha", tags=["auth"])
async def alterar_senha(
    payload: AlterarSenhaPayload,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Altera a senha do próprio usuário."""
    user = auth_db.get_usuario(current_user["sub"])
    if not user or not auth.verify_password(payload.senha_atual, user["senha_hash"]):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    new_hash = auth.hash_password(payload.nova_senha)
    auth_db.alterar_senha_hash(user["id"], new_hash)

    auth_db.log_acao(
        "senha_alterada",
        usuario_id=user["id"],
        empresa_id=user["empresa_id"],
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True, "detail": "Senha alterada com sucesso."}


# =========================================================================== #
#  ROTAS SUPERADMIN — /admin/*                                                  #
# =========================================================================== #

@app.get("/admin/empresas", tags=["admin"])
async def listar_empresas(
    _: dict = Depends(require_superadmin),
):
    """Lista todas as empresas cadastradas."""
    empresas = auth_db.listar_empresas(apenas_ativas=False)
    result = []
    for e in empresas:
        # Conta usuarios ativos
        usuarios = auth_db.listar_usuarios_empresa(e["id"], apenas_ativos=True)
        result.append({**e, "total_usuarios": len(usuarios)})
    return result


@app.post("/admin/empresas", tags=["admin"])
async def criar_empresa(
    payload: EmpresaCreate,
    current_user: dict = Depends(require_superadmin),
    request: Request = None,
):
    """
    Cria uma empresa e seu primeiro admin em uma única operação.
    Apenas o superadmin pode criar empresas.
    """
    # Valida email unico
    if auth_db.email_existe(payload.email_admin):
        raise HTTPException(
            status_code=409,
            detail=f"E-mail '{payload.email_admin}' já está cadastrado no sistema.",
        )

    # Cria empresa
    empresa = auth_db.criar_empresa(
        razao_social=payload.razao_social,
        email_admin=payload.email_admin,
        cnpj=payload.cnpj,
        created_by=current_user["sub"],
    )

    # Cria admin da empresa
    senha_hash = auth.hash_password(payload.senha_admin)
    admin_user = auth_db.criar_usuario(
        empresa_id=empresa["id"],
        nome=payload.nome_admin,
        email=payload.email_admin,
        senha_hash=senha_hash,
        role="admin",
        created_by=current_user["sub"],
    )

    auth_db.log_acao(
        "empresa_criada",
        usuario_id=current_user["sub"],
        empresa_id=empresa["id"],
        detalhes=f"razao_social={payload.razao_social}",
        ip=request.client.host if request and request.client else None,
    )

    logger.info("Empresa criada: %s [%s]", payload.razao_social, empresa["id"])
    return {
        "empresa": empresa,
        "admin":   {k: v for k, v in admin_user.items() if k != "senha_hash"},
    }


@app.delete("/admin/empresas/{empresa_id}", tags=["admin"])
async def desativar_empresa(
    empresa_id: str,
    current_user: dict = Depends(require_superadmin),
    request: Request = None,
):
    """Desativa uma empresa (e seus usuários ficam sem acesso)."""
    ok = auth_db.desativar_empresa(empresa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    auth_db.log_acao(
        "empresa_desativada",
        usuario_id=current_user["sub"],
        empresa_id=empresa_id,
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True}


@app.put("/admin/empresas/{empresa_id}/reativar", tags=["admin"])
async def reativar_empresa(
    empresa_id: str,
    current_user: dict = Depends(require_superadmin),
):
    """Reativa uma empresa."""
    ok = auth_db.reativar_empresa(empresa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    auth_db.log_acao("empresa_reativada", usuario_id=current_user["sub"], empresa_id=empresa_id)
    return {"ok": True}


@app.put("/admin/empresas/{empresa_id}", tags=["admin"])
async def atualizar_empresa(
    empresa_id: str,
    payload: dict,
    current_user: dict = Depends(require_superadmin),
    request: Request = None,
):
    """Atualiza razao_social, cnpj e/ou email_admin de uma empresa."""
    campos = {k: v for k, v in payload.items() if k in {"razao_social", "cnpj", "email_admin"}}
    if not campos:
        raise HTTPException(status_code=422, detail="Nenhum campo válido para atualizar.")
    ok = auth_db.atualizar_empresa(empresa_id, campos)
    if not ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    auth_db.log_acao(
        "empresa_atualizada",
        usuario_id=current_user["sub"],
        empresa_id=empresa_id,
        detalhes=f"Campos atualizados: {', '.join(campos.keys())}",
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True}


@app.put("/admin/usuarios/{user_id}", tags=["admin"])
async def atualizar_usuario_admin(
    user_id: str,
    payload: dict,
    current_user: dict = Depends(require_superadmin),
    request: Request = None,
):
    """Atualiza nome, email e/ou role de qualquer usuário (superadmin only)."""
    campos = {k: v for k, v in payload.items() if k in {"nome", "email", "role"}}
    if not campos:
        raise HTTPException(status_code=422, detail="Nenhum campo válido para atualizar.")
    if "role" in campos and campos["role"] not in {"admin", "user"}:
        raise HTTPException(status_code=422, detail="Role inválido. Use 'admin' ou 'user'.")
    ok = auth_db.atualizar_usuario(user_id, campos)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    auth_db.log_acao(
        "usuario_atualizado",
        usuario_id=current_user["sub"],
        empresa_id=current_user["empresa_id"],
        detalhes=f"Usuário {user_id} — campos: {', '.join(campos.keys())}",
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True}


@app.get("/admin/audit", tags=["admin"])
async def audit_global(
    limit: int = 100,
    _: dict = Depends(require_superadmin),
):
    """Audit log completo (superadmin only)."""
    return auth_db.listar_audit(limit=limit)


# =========================================================================== #
#  ROTAS DE EMPRESA — /empresa/*                                                #
# =========================================================================== #

@app.get("/empresa/usuarios", tags=["empresa"])
async def listar_usuarios(
    current_user: dict = Depends(require_admin),
):
    """Lista usuários da empresa do usuário autenticado."""
    empresa_id = current_user["empresa_id"]
    return auth_db.listar_usuarios_empresa(empresa_id, apenas_ativos=False)


@app.post("/empresa/usuarios", tags=["empresa"])
async def criar_usuario(
    payload: UserCreate,
    current_user: dict = Depends(require_admin),
    request: Request = None,
):
    """Cria um usuário na empresa do administrador autenticado."""
    empresa_id = current_user["empresa_id"]

    # Superadmin nao pode criar usuarios em empresas via este endpoint
    if current_user["role"] == "superadmin":
        raise HTTPException(
            status_code=400,
            detail="Use POST /admin/empresas para criar empresas e seus admins.",
        )

    if auth_db.email_existe(payload.email):
        raise HTTPException(
            status_code=409,
            detail=f"E-mail '{payload.email}' já está cadastrado.",
        )

    # Admin nao pode criar outro superadmin
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role deve ser 'admin' ou 'user'.")

    senha_hash = auth.hash_password(payload.senha)
    user = auth_db.criar_usuario(
        empresa_id=empresa_id,
        nome=payload.nome,
        email=payload.email,
        senha_hash=senha_hash,
        role=payload.role,
        created_by=current_user["sub"],
    )

    auth_db.log_acao(
        "usuario_criado",
        usuario_id=current_user["sub"],
        empresa_id=empresa_id,
        detalhes=f"novo_usuario={payload.email} role={payload.role}",
        ip=request.client.host if request and request.client else None,
    )
    return {k: v for k, v in user.items() if k != "senha_hash"}


@app.delete("/empresa/usuarios/{user_id}", tags=["empresa"])
async def desativar_usuario(
    user_id: str,
    current_user: dict = Depends(require_admin),
    request: Request = None,
):
    """Desativa um usuário da empresa."""
    empresa_id = current_user["empresa_id"]

    # Não pode desativar a si mesmo
    if user_id == current_user["sub"]:
        raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta.")

    ok = auth_db.desativar_usuario(user_id, empresa_id=empresa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado na sua empresa.")

    auth_db.log_acao(
        "usuario_desativado",
        usuario_id=current_user["sub"],
        empresa_id=empresa_id,
        detalhes=f"user_id={user_id}",
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True}


@app.put("/empresa/usuarios/{user_id}/reativar", tags=["empresa"])
async def reativar_usuario(
    user_id: str,
    current_user: dict = Depends(require_admin),
):
    """Reativa um usuário da empresa."""
    empresa_id = current_user["empresa_id"]
    ok = auth_db.reativar_usuario(user_id, empresa_id=empresa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    auth_db.log_acao("usuario_reativado", usuario_id=current_user["sub"], empresa_id=empresa_id)
    return {"ok": True}


@app.get("/empresa/audit", tags=["empresa"])
async def audit_empresa(
    limit: int = 50,
    current_user: dict = Depends(require_admin),
):
    """Audit log da empresa."""
    return auth_db.listar_audit(empresa_id=current_user["empresa_id"], limit=limit)


@app.get("/empresa/sessoes", tags=["empresa"])
async def listar_sessoes(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Lista sessões de extração recentes da empresa."""
    return auth_db.listar_sessoes(current_user["empresa_id"], limit=limit)


# =========================================================================== #
#  Dashboard API — usada pelo Streamlit Cloud                                   #
# =========================================================================== #

@app.get("/dashboard/ultima-sessao", tags=["dashboard"])
async def dashboard_ultima_sessao(
    current_user: dict = Depends(get_current_user),
):
    """
    Retorna a sessão mais recente da empresa com todos os resultados.
    Consumida pelo Streamlit Cloud (dashboard.py).
    """
    import json as _json_mod
    sessao = auth_db.get_ultima_sessao(current_user["empresa_id"])
    if not sessao:
        return None
    return {
        "id":        sessao["id"],
        "tema":      sessao["tema"],
        "timestamp": sessao["timestamp"],
        "results":   _json_mod.loads(sessao["results_json"]).get("results", []),
    }


@app.get("/dashboard/sessoes", tags=["dashboard"])
async def dashboard_sessoes(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Lista as sessões recentes (sem results_json) para o histórico do dashboard."""
    return auth_db.listar_sessoes(current_user["empresa_id"], limit=limit)


@app.get("/dashboard/sessoes/{sessao_id}", tags=["dashboard"])
async def dashboard_sessao_por_id(
    sessao_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Retorna uma sessão específica pelo ID (valida pertencimento à empresa)."""
    import json as _json_mod
    sessao = auth_db.get_sessao(sessao_id, current_user["empresa_id"])
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return {
        "id":        sessao["id"],
        "tema":      sessao["tema"],
        "timestamp": sessao["timestamp"],
        "results":   _json_mod.loads(sessao["results_json"]).get("results", []),
    }


# =========================================================================== #
#  LGPD — direito ao esquecimento                                               #
# =========================================================================== #

@app.delete("/lgpd/apagar-minha-conta", tags=["lgpd"])
async def apagar_minha_conta(
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    LGPD — Anonimiza todos os dados pessoais do usuário autenticado.
    O registro é mantido (para integridade do audit_log) mas o PII é removido.
    O token JWT atual torna-se inválido após esta operação.
    """
    user_id = current_user["sub"]
    auth_db.log_acao(
        "lgpd_apagar_conta",
        usuario_id=user_id,
        empresa_id=current_user["empresa_id"],
        detalhes="Solicitacao de apagamento de dados pelo proprio usuario",
        ip=request.client.host if request and request.client else None,
    )
    ok = auth_db.apagar_dados_usuario(user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao processar solicitação.")
    return {"ok": True, "detail": "Seus dados foram removidos conforme a LGPD."}


@app.post("/lgpd/consent-log", tags=["lgpd"])
async def lgpd_consent_log(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Registra no audit_log que o usuário confirmou a base legal
    para processar currículos nesta sessão de trabalho.
    Chamado automaticamente pelo frontend antes de cada lote de CVs.
    """
    versao = payload.get("versao_politica", "1.0")
    contexto = payload.get("contexto", "processamento_curriculos")
    auth_db.log_acao(
        "lgpd_consent_processamento",
        usuario_id=current_user["sub"],
        empresa_id=current_user["empresa_id"],
        detalhes=f"Aceite da base legal para {contexto} | Política v{versao}",
        ip=request.client.host if request and request.client else None,
    )
    return {"ok": True}


# =========================================================================== #
#  SETTINGS (protegido — admin+)                                                #
# =========================================================================== #

@app.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    db = settings_db.get_all()
    user = db.get("GMAIL_USER", "")
    pwd  = db.get("GMAIL_APP_PASSWORD", "")
    out_user = db.get("OUTLOOK_USER", "")
    out_pwd  = db.get("OUTLOOK_APP_PASSWORD", "")
    return {
        "gmail_user":           user,
        "gmail_app_password":   "__SAVED__" if pwd else "",
        "gmail_configured":     bool(user and pwd),
        "outlook_user":         out_user,
        "outlook_app_password": "__SAVED__" if out_pwd else "",
        "outlook_configured":   bool(out_user and out_pwd),
        "email_from_name":      db.get("EMAIL_FROM_NAME", "BTExtract · RH Inteligente"),
        "gemini_model":         db.get("GEMINI_MODEL", config.GEMINI_MODEL),
        "email_provider":       db.get("EMAIL_PROVIDER", "gmail"),
        "gemini_managed":       config.GEMINI_MANAGED,
        "gemini_configured":    bool(config.GEMINI_API_KEY),
    }


@app.post("/settings")
async def save_settings(
    payload: SettingsPayload,
    current_user: dict = Depends(require_admin),
):
    import ai_processor

    to_save: dict[str, str] = {}
    updated: list[str] = []
    old_model = settings_db.get("GEMINI_MODEL", config.GEMINI_MODEL)

    if payload.gmail_user is not None:
        to_save["GMAIL_USER"] = payload.gmail_user.strip()
        updated.append("GMAIL_USER")
    pwd_gmail = payload.gmail_app_password or ""
    if pwd_gmail and pwd_gmail != "__SAVED__" and pwd_gmail.strip("•").strip():
        to_save["GMAIL_APP_PASSWORD"] = pwd_gmail.strip()
        updated.append("GMAIL_APP_PASSWORD")
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

    importlib.reload(config)
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
async def test_email(
    payload: SettingsPayload,
    current_user: dict = Depends(require_admin),
):
    provider = (payload.email_provider or settings_db.get("EMAIL_PROVIDER") or "gmail").strip()

    if provider == "outlook":
        raw_user  = (payload.outlook_user or "").strip()
        test_user = raw_user or settings_db.get("OUTLOOK_USER", "")
        raw_pwd   = (payload.outlook_app_password or "").strip()
        db_pwd_key = "OUTLOOK_APP_PASSWORD"
    else:
        raw_user  = (payload.gmail_user or "").strip()
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
        import ssl as _ssl
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from_name = settings_db.get("EMAIL_FROM_NAME", config.EMAIL_FROM_NAME)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "BTExtract — Teste de configuração"
        msg["From"]    = f"{from_name} <{test_user}>"
        msg["To"]      = test_user
        html_body = (
            "<p>Olá! Se você recebeu este e-mail, o BTExtract está configurado "
            "corretamente para enviar relatórios de triagem.</p>"
            "<p><b>BTExtract · RH Inteligente</b></p>"
        )
        msg.attach(MIMEText("Este e-mail requer HTML.", "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        _SMTP_MAP = {"gmail": "smtp.gmail.com", "outlook": "smtp.office365.com"}
        smtp_host = _SMTP_MAP.get(provider, "smtp.gmail.com")
        ctx = _ssl.create_default_context()
        with smtplib.SMTP(smtp_host, 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(test_user, test_pwd)
            server.sendmail(test_user, test_user, msg.as_string())

        return {"success": True, "detail": {"status": "sent", "to": test_user}}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


# =========================================================================== #
#  /extract — processa currículos (protegido)                                   #
# =========================================================================== #

@app.post("/extract")
async def extract(
    request: Request,
    files: Annotated[list[UploadFile], File(description="Arquivos de currículo")],
    job_description:     Annotated[Optional[str], Form()] = None,
    send_email_flag:     Annotated[Optional[str], Form(alias="send_email")] = None,
    destinatario:        Annotated[Optional[str], Form()] = None,
    tema:                Annotated[Optional[str], Form()] = None,
    nome_recrutador:     Annotated[Optional[str], Form()] = None,
    empresa_recrutadora: Annotated[Optional[str], Form()] = None,
    contexto_adicional:  Annotated[Optional[str], Form()] = None,
    current_user: dict = Depends(get_current_user),
):
    """Processa um ou mais arquivos de currículo."""
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
            detail="GEMINI_API_KEY não configurada."
        )

    t_start = time.monotonic()

    uploaded_names = [f.filename for f in files if f.filename]
    if uploaded_names:
        settings_db.delete_comments_for_files(uploaded_names)

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

    # ── Persiste sessão no banco (multi-tenant) ──
    try:
        import json as _json
        _session = {
            "tema":      job_description[:120] if job_description else (tema or "Triagem Geral"),
            "timestamp": datetime.now().isoformat(),
            "results":   [r.model_dump() for r in results],
        }
        session_json = _json.dumps(_session, ensure_ascii=False, default=str)

        # Salva no banco de dados (multi-tenant)
        auth_db.salvar_sessao(
            empresa_id=current_user["empresa_id"],
            usuario_id=current_user["sub"],
            tema=_session["tema"],
            results_json=session_json,
        )

        # Mantém compatibilidade com Streamlit local (last_session.json)
        try:
            _SESSION_PATH.write_text(session_json, encoding="utf-8")
        except Exception:
            pass
    except Exception as _e:
        logger.warning("Falha ao salvar sessão: %s", _e)

    response_body: dict = {
        "request_id":       req_id,
        "total":            len(results),
        "success":          n_ok,
        "errors":           n_err,
        "total_elapsed_ms": elapsed_ms,
        "results":          [r.model_dump() for r in results],
        "email_sent":       False,
    }

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
                results_dicts = [r.model_dump() for r in results]
                xlsx_bytes = generate_excel_report(
                    results=results_dicts,
                    tema=tema or "Triagem Geral",
                    nome_recrutador=nome_recrutador,
                    empresa_recrutadora=empresa_recrutadora,
                )
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                attachments = [{
                    "filename": f"BTExtract_Triagem_{ts}.xlsx",
                    "data":     xlsx_bytes,
                    "mimetype": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                }]
                mail_result = send_email(
                    to_email=destinatario,
                    subject=email_content["subject"],
                    html_body=email_content["html_body"],
                    attachments=attachments,
                )
                response_body["email_sent"]    = True
                response_body["email_status"]  = mail_result
                response_body["email_subject"] = email_content["subject"]
                logger.info("E-mail enviado para %s", destinatario, extra={"ce_request_id": req_id})
            except Exception as exc:
                logger.error("Falha ao enviar e-mail: %s", exc, extra={"ce_request_id": req_id})
                response_body["email_error"] = str(exc)

    logger.info(
        "Requisição finalizada | ok=%d err=%d elapsed=%dms email=%s",
        n_ok, n_err, elapsed_ms, response_body["email_sent"],
        extra={"ce_request_id": req_id},
    )
    return JSONResponse(content=response_body)


# =========================================================================== #
#  /extract/file — processa UM arquivo (sem salvar sessão)                      #
#  Usado pelo frontend em modo Vercel: uma chamada por arquivo, progresso live  #
# =========================================================================== #

@app.post("/extract/file")
async def extract_single_file(
    request: Request,
    file:            Annotated[UploadFile, File(description="Arquivo de currículo")],
    job_description: Annotated[Optional[str], Form()] = None,
    current_user: dict = Depends(get_current_user),
):
    """Processa um único arquivo e retorna o resultado (sem persistir sessão)."""
    req_id = request.state.request_id
    if not config.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY não configurada.")
    content = await file.read()
    result = _process_one(
        file_bytes=content,
        filename=file.filename or "arquivo",
        job_description=job_description or None,
        request_id=req_id,
    )
    return JSONResponse(content=result.model_dump())


@app.post("/sessao/salvar")
async def salvar_sessao_endpoint(
    payload: SalvarSessaoPayload,
    current_user: dict = Depends(get_current_user),
):
    """
    Salva uma sessão de extração com todos os resultados acumulados.
    O frontend chama este endpoint após processar todos os arquivos via /extract/file.
    """
    import json as _json
    tema = payload.tema or "Triagem Geral"
    session_data = {
        "tema":      tema,
        "timestamp": datetime.now().isoformat(),
        "results":   payload.results,
    }
    session_json = _json.dumps(session_data, ensure_ascii=False, default=str)
    try:
        sessao_id = auth_db.salvar_sessao(
            empresa_id=current_user["empresa_id"],
            usuario_id=current_user["sub"],
            tema=tema,
            results_json=session_json,
        )
        try:
            _SESSION_PATH.write_text(session_json, encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "sessao_id": sessao_id}
    except Exception as exc:
        logger.warning("Falha ao salvar sessão: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao salvar sessão.")


# =========================================================================== #
#  /email/send (protegido)                                                      #
# =========================================================================== #

@app.post("/email/send")
async def send_triagem_email(
    payload: EmailSendPayload,
    current_user: dict = Depends(get_current_user),
):
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
                pr_results.append(
                    PR(filename=fname, status="error",
                       error=f"Dados incompletos: {str(ve)[:120]}")
                )

        if not pr_results:
            raise HTTPException(status_code=400, detail="Nenhum resultado válido.")

        dest_nome = payload.destinatario_nome or (
            payload.destinatario.split("@")[0]
            .replace(".", " ").replace("_", " ").title()
        )
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

        attachments = []
        if payload.incluir_excel:
            xlsx_bytes = generate_excel_report(
                results=payload.results,
                tema=payload.tema or "Triagem Geral",
                nome_recrutador=payload.nome_recrutador,
                empresa_recrutadora=payload.empresa_recrutadora,
            )
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            attachments = [{
                "filename": f"BTExtract_Triagem_{ts}.xlsx",
                "data":     xlsx_bytes,
                "mimetype": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            }]

        mail_result = send_email(
            to_email=payload.destinatario,
            subject=email_content["subject"],
            html_body=email_content["html_body"],
            attachments=attachments if attachments else None,
            cc=payload.cc or None,
        )

        logger.info("E-mail de triagem enviado para %s", payload.destinatario)
        return {"sent": True, "status": mail_result, "subject": email_content["subject"]}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao enviar e-mail: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# =========================================================================== #
#  /export/excel (protegido)                                                    #
# =========================================================================== #

@app.post("/export/excel")
async def export_excel(
    payload: ExcelExportPayload,
    current_user: dict = Depends(get_current_user),
):
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
        filename = f"BTExtract_Triagem_{ts}.xlsx"
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


# =========================================================================== #
#  /comments (protegido)                                                        #
# =========================================================================== #

@app.get("/comments")
async def get_comments(
    filenames: str = "",
    current_user: dict = Depends(get_current_user),
):
    if not filenames:
        return JSONResponse(content={})
    names = [f.strip() for f in filenames.split(",") if f.strip()]
    return JSONResponse(content=settings_db.get_comments_for_files(names))


@app.post("/comments")
async def save_comment(
    payload: CommentPayload,
    current_user: dict = Depends(get_current_user),
):
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
        reload=not is_frozen(),
        log_level="info",
    )
