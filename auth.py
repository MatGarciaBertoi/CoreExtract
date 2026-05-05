"""
auth.py
══════════════════════════════════════════════════════════════════════════════
JWT (HS256) + bcrypt para o sistema de autenticacao multi-tenant CoreExtract.

Dependencias (requirements.txt):
  python-jose[cryptography]
  passlib[bcrypt]

Roles:
  superadmin  → dono do sistema  (empresa_id = SYSTEM_EMPRESA_ID)
  admin       → admin da empresa (criado pelo superadmin)
  user        → colaborador      (criado pelo admin da empresa)
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

import auth_db

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer  = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


# ── Importa config de forma lazy para evitar importacao circular ──────────────

def _secret() -> str:
    import config
    return config.JWT_SECRET


def _expire_hours() -> int:
    import config
    return config.JWT_EXPIRE_HOURS


# ── Senha ─────────────────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """Gera hash bcrypt de uma senha em texto plano."""
    return _pwd_ctx.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Valida uma senha contra um hash bcrypt."""
    return _pwd_ctx.verify(plaintext, hashed)


# ── Token JWT ─────────────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    role: str,
    empresa_id: str,
    nome: str = "",
) -> str:
    """
    Cria um JWT com os dados do usuario. Expiracao controlada por
    config.JWT_EXPIRE_HOURS (padrao: 8h).
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=_expire_hours())
    payload = {
        "sub":        user_id,
        "email":      email,
        "role":       role,
        "empresa_id": empresa_id,
        "nome":       nome,
        "exp":        expire,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decodifica e valida um JWT. Levanta JWTError em caso de falha
    (token invalido, expirado, assinatura incorreta).
    """
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])


# ── Dependencias FastAPI ──────────────────────────────────────────────────────

async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    Dependency: extrai e valida o JWT do header 'Authorization: Bearer <token>'.
    Retorna o payload do token como dicionario.
    Uso: route(current_user: dict = Depends(get_current_user))
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacao necessario.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado. Faca login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Garante que o usuario ainda existe e esta ativo no banco
    user = auth_db.get_usuario(payload.get("sub", ""))
    if not user or not user.get("ativo"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inativo ou removido.",
        )
    return payload


async def require_superadmin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency: exige role == 'superadmin'."""
    if current_user.get("role") != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador do sistema.",
        )
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency: exige role in ('superadmin', 'admin')."""
    if current_user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return current_user


# ── Bootstrap do superadmin ───────────────────────────────────────────────────

def bootstrap_superadmin() -> None:
    """
    Cria o superadmin a partir das credenciais no .env se ainda nao existir.
    Chamado UMA VEZ no startup da aplicacao (via lifespan do FastAPI).

    Se SUPERADMIN_EMAIL ou SUPERADMIN_SENHA estiverem vazios no .env,
    a funcao retorna silenciosamente (nao levanta excecao).
    """
    import config

    email = (config.SUPERADMIN_EMAIL or "").strip()
    senha = (config.SUPERADMIN_SENHA or "").strip()

    if not email or not senha:
        return  # Superadmin nao configurado — skip silencioso

    # Ja existe?
    existing = auth_db.get_usuario_por_email(email)
    if existing:
        return

    from utils.paths import DB_PATH

    # Garante que a empresa-sistema existe (INSERT OR IGNORE)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO empresas (id, razao_social, email_admin)
            VALUES (?, '[SISTEMA] Bertoi Informatica', ?)
            """,
            (auth_db.SYSTEM_EMPRESA_ID, email),
        )
        conn.commit()
    finally:
        conn.close()

    # Cria o superadmin
    senha_hash = hash_password(senha)
    auth_db.criar_usuario(
        empresa_id=auth_db.SYSTEM_EMPRESA_ID,
        nome="Superadmin",
        email=email,
        senha_hash=senha_hash,
        role="superadmin",
        created_by="system",
    )
    auth_db.log_acao(
        "bootstrap_superadmin",
        detalhes=f"Superadmin criado: {email}",
    )
