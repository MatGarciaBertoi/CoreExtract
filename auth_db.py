"""
auth_db.py
══════════════════════════════════════════════════════════════════════════════
Gerencia tabelas multi-tenant: empresas, usuarios, audit_log, sessoes.
Thread-safe via lock module-level (mesmo padrao do settings_db.py).

Modelo:
  - superadmin  → dono do sistema (criado via .env), empresa_id = SYSTEM_ID
  - admin       → administrador de uma empresa (criado pelo superadmin)
  - user        → colaborador de uma empresa (criado pelo admin da empresa)

LGPD:
  - Dados minimos coletados (nome + email + cargo)
  - Senhas NUNCA armazenadas em texto plano (bcrypt via auth.py)
  - lgpd_consent_at registrado no momento do cadastro
  - Audit log completo de todas as acoes sensiveis
  - Endpoint de exclusao de dados (anonimizacao) por usuario
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from utils.paths import DB_PATH as _DB_PATH

_lock = threading.Lock()

# ID especial para a empresa-sistema (superadmin)
SYSTEM_EMPRESA_ID = "00000000-0000-0000-0000-000000000000"


# ── Conexao ───────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")   # FK desativada p/ flexibilidade de migracao
    return conn


# ── Migracao ──────────────────────────────────────────────────────────────────

def _migrate() -> None:
    """Cria todas as tabelas de autenticacao se ainda nao existirem. Idempotente."""
    with _lock:
        conn = _connect()
        try:
            conn.executescript("""
                -- Empresas cadastradas no sistema
                CREATE TABLE IF NOT EXISTS empresas (
                    id            TEXT PRIMARY KEY,
                    razao_social  TEXT NOT NULL,
                    cnpj          TEXT,
                    email_admin   TEXT NOT NULL,
                    ativo         INTEGER NOT NULL DEFAULT 1,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    created_by    TEXT
                );

                -- Usuarios (todos os roles)
                CREATE TABLE IF NOT EXISTS usuarios (
                    id              TEXT PRIMARY KEY,
                    empresa_id      TEXT NOT NULL,
                    nome            TEXT NOT NULL,
                    email           TEXT UNIQUE NOT NULL,
                    senha_hash      TEXT NOT NULL,
                    role            TEXT NOT NULL DEFAULT 'user',
                    ativo           INTEGER NOT NULL DEFAULT 1,
                    lgpd_consent_at TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    created_by      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_usuarios_empresa ON usuarios(empresa_id);
                CREATE INDEX IF NOT EXISTS idx_usuarios_email   ON usuarios(email);

                -- Audit log — nao apagar registros, anonimizar apenas o PII
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id  TEXT,
                    empresa_id  TEXT,
                    acao        TEXT NOT NULL,
                    detalhes    TEXT,
                    ip          TEXT,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_audit_empresa ON audit_log(empresa_id);
                CREATE INDEX IF NOT EXISTS idx_audit_usuario ON audit_log(usuario_id);

                -- Sessoes de extracao (substitui last_session.json no modo web)
                CREATE TABLE IF NOT EXISTS sessoes (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id   TEXT NOT NULL,
                    usuario_id   TEXT NOT NULL,
                    tema         TEXT DEFAULT 'Triagem Geral',
                    timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
                    results_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessoes_empresa ON sessoes(empresa_id);
            """)
            conn.commit()
        finally:
            conn.close()


_migrate()


# ── Empresas ──────────────────────────────────────────────────────────────────

def criar_empresa(
    razao_social: str,
    email_admin: str,
    cnpj: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict:
    """Cria uma nova empresa. Retorna dict com id e dados basicos."""
    empresa_id = str(uuid.uuid4())
    cnpj_clean = cnpj.strip() if cnpj else None
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO empresas (id, razao_social, cnpj, email_admin, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (empresa_id, razao_social.strip(), cnpj_clean,
                 email_admin.strip().lower(), created_by),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "id": empresa_id,
        "razao_social": razao_social,
        "cnpj": cnpj_clean,
        "email_admin": email_admin,
    }


def get_empresa(empresa_id: str) -> Optional[dict]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM empresas WHERE id = ?", (empresa_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def listar_empresas(apenas_ativas: bool = True) -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM empresas"
            if apenas_ativas:
                q += " WHERE ativo = 1"
            q += " ORDER BY razao_social"
            return [dict(r) for r in conn.execute(q).fetchall()]
        finally:
            conn.close()


def desativar_empresa(empresa_id: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE empresas SET ativo = 0 WHERE id = ?", (empresa_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def reativar_empresa(empresa_id: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE empresas SET ativo = 1 WHERE id = ?", (empresa_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def atualizar_empresa(empresa_id: str, campos: dict) -> bool:
    """Atualiza razao_social, cnpj e/ou email_admin de uma empresa."""
    permitidos = {"razao_social", "cnpj", "email_admin"}
    updates = {k: v for k, v in campos.items() if k in permitidos}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [empresa_id]
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                f"UPDATE empresas SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# ── Usuarios ──────────────────────────────────────────────────────────────────

def criar_usuario(
    empresa_id: str,
    nome: str,
    email: str,
    senha_hash: str,
    role: str = "user",
    created_by: Optional[str] = None,
) -> dict:
    """
    Cria um usuario. lgpd_consent_at e registrado automaticamente (momento do cadastro).
    Retorna dict com campos basicos (sem senha_hash).
    """
    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO usuarios
                    (id, empresa_id, nome, email, senha_hash, role, lgpd_consent_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, empresa_id, nome.strip(), email.strip().lower(),
                 senha_hash, role, now_iso, created_by),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "id": user_id,
        "empresa_id": empresa_id,
        "nome": nome,
        "email": email,
        "role": role,
    }


def get_usuario_por_email(email: str) -> Optional[dict]:
    """Busca usuario ativo pelo e-mail. Retorna None se nao encontrado ou inativo."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM usuarios WHERE email = ? AND ativo = 1",
                (email.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_usuario(user_id: str) -> Optional[dict]:
    """Busca usuario por ID (independente de status)."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM usuarios WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def listar_usuarios_empresa(empresa_id: str, apenas_ativos: bool = True) -> list[dict]:
    """Lista usuarios de uma empresa sem expor senha_hash."""
    with _lock:
        conn = _connect()
        try:
            q = """
                SELECT id, nome, email, role, ativo, lgpd_consent_at, created_at
                FROM usuarios
                WHERE empresa_id = ?
            """
            params: list = [empresa_id]
            if apenas_ativos:
                q += " AND ativo = 1"
            q += " ORDER BY nome"
            return [dict(r) for r in conn.execute(q, params).fetchall()]
        finally:
            conn.close()


def desativar_usuario(user_id: str, empresa_id: Optional[str] = None) -> bool:
    """
    Desativa um usuario. Se empresa_id fornecido, verifica pertencimento
    (impede que admin de empresa A desative usuario de empresa B).
    """
    with _lock:
        conn = _connect()
        try:
            if empresa_id:
                cur = conn.execute(
                    "UPDATE usuarios SET ativo = 0 WHERE id = ? AND empresa_id = ?",
                    (user_id, empresa_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE usuarios SET ativo = 0 WHERE id = ?", (user_id,)
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def reativar_usuario(user_id: str, empresa_id: Optional[str] = None) -> bool:
    with _lock:
        conn = _connect()
        try:
            if empresa_id:
                cur = conn.execute(
                    "UPDATE usuarios SET ativo = 1 WHERE id = ? AND empresa_id = ?",
                    (user_id, empresa_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE usuarios SET ativo = 1 WHERE id = ?", (user_id,)
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def atualizar_usuario(user_id: str, campos: dict) -> bool:
    """Atualiza nome, email e/ou role de um usuário (superadmin only)."""
    permitidos = {"nome", "email", "role"}
    updates = {k: v for k, v in campos.items() if k in permitidos}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                f"UPDATE usuarios SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def apagar_dados_usuario(user_id: str) -> bool:
    """
    LGPD — direito ao esquecimento.
    Anonimiza o PII mas preserva o registro para integridade do audit_log.
    Senhas sao esvaziadas; email anonimizado para manter UNIQUE constraint.
    """
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE usuarios
                SET nome       = '[dados removidos]',
                    email      = 'removido_' || id || '@apagado.local',
                    senha_hash = '',
                    ativo      = 0
                WHERE id = ?
                """,
                (user_id,),
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()


def email_existe(email: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM usuarios WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
            return row is not None
        finally:
            conn.close()


# ── Sessoes ───────────────────────────────────────────────────────────────────

def salvar_sessao(
    empresa_id: str,
    usuario_id: str,
    tema: str,
    results_json: str,
) -> int:
    """Persiste resultados de uma extracao. Retorna o ID da sessao."""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO sessoes (empresa_id, usuario_id, tema, results_json)
                VALUES (?, ?, ?, ?)
                """,
                (empresa_id, usuario_id, tema, results_json),
            )
            conn.commit()
            return cur.lastrowid  # type: ignore[return-value]
        finally:
            conn.close()


def get_ultima_sessao(empresa_id: str) -> Optional[dict]:
    """Retorna a sessao mais recente da empresa (para o Dashboard)."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM sessoes
                WHERE empresa_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (empresa_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def listar_sessoes(empresa_id: str, limit: int = 20) -> list[dict]:
    """Lista sessoes recentes de uma empresa (sem results_json para economizar banda)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, tema, timestamp, usuario_id
                FROM sessoes
                WHERE empresa_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (empresa_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_sessao(sessao_id: int, empresa_id: str) -> Optional[dict]:
    """Retorna uma sessao especifica (validando pertencimento a empresa)."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM sessoes WHERE id = ? AND empresa_id = ?",
                (sessao_id, empresa_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# ── Audit Log ─────────────────────────────────────────────────────────────────

def log_acao(
    acao: str,
    usuario_id: Optional[str] = None,
    empresa_id: Optional[str] = None,
    detalhes: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Registra uma acao no audit log. Nunca levanta excecao (nao bloqueia operacao principal)."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO audit_log (usuario_id, empresa_id, acao, detalhes, ip)
                VALUES (?, ?, ?, ?, ?)
                """,
                (usuario_id, empresa_id, acao, detalhes, ip),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def listar_audit(empresa_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            if empresa_id:
                rows = conn.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE empresa_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (empresa_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
