"""
_auth_db_pg.py — implementação PostgreSQL de auth_db.
Usado automaticamente quando DATABASE_URL está definida (deploy Vercel + Supabase).
API pública idêntica ao auth_db.py (SQLite).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SYSTEM_EMPRESA_ID = "00000000-0000-0000-0000-000000000000"


def _connect():
    return psycopg2.connect(DATABASE_URL, connect_timeout=8)


def _to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _to_dicts(rows) -> list[dict]:
    return [_to_dict(r) for r in rows]


# ── Empresas ──────────────────────────────────────────────────────────────────

def criar_empresa(
    razao_social: str,
    email_admin: str,
    cnpj: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict:
    empresa_id = str(uuid.uuid4())
    cnpj_clean = cnpj.strip() if cnpj else None
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO empresas (id, razao_social, cnpj, email_admin, created_by) "
                "VALUES (%s, %s, %s, %s, %s)",
                (empresa_id, razao_social.strip(), cnpj_clean,
                 email_admin.strip().lower(), created_by),
            )
    finally:
        conn.close()
    return {"id": empresa_id, "razao_social": razao_social, "cnpj": cnpj_clean, "email_admin": email_admin}


def get_empresa(empresa_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM empresas WHERE id = %s", (empresa_id,))
        return _to_dict(cur.fetchone())
    finally:
        conn.close()


def listar_empresas(apenas_ativas: bool = True) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        q = "SELECT * FROM empresas"
        if apenas_ativas:
            q += " WHERE ativo = 1"
        q += " ORDER BY razao_social"
        cur.execute(q)
        return _to_dicts(cur.fetchall())
    finally:
        conn.close()


def desativar_empresa(empresa_id: str) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("UPDATE empresas SET ativo = 0 WHERE id = %s", (empresa_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def reativar_empresa(empresa_id: str) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("UPDATE empresas SET ativo = 1 WHERE id = %s", (empresa_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def atualizar_empresa(empresa_id: str, campos: dict) -> bool:
    permitidos = {"razao_social", "cnpj", "email_admin"}
    updates = {k: v for k, v in campos.items() if k in permitidos}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [empresa_id]
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE empresas SET {set_clause} WHERE id = %s", values)
            return cur.rowcount > 0
    finally:
        conn.close()


def ensure_sistema_empresa(email_admin: str) -> None:
    """Garante que a empresa-sistema (superadmin) existe. Idempotente."""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO empresas (id, razao_social, email_admin) "
                "VALUES (%s, '[SISTEMA] Bertoi Informatica', %s) "
                "ON CONFLICT (id) DO NOTHING",
                (SYSTEM_EMPRESA_ID, email_admin),
            )
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
    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO usuarios "
                "(id, empresa_id, nome, email, senha_hash, role, lgpd_consent_at, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (user_id, empresa_id, nome.strip(), email.strip().lower(),
                 senha_hash, role, now_iso, created_by),
            )
    finally:
        conn.close()
    return {"id": user_id, "empresa_id": empresa_id, "nome": nome, "email": email, "role": role}


def get_usuario_por_email(email: str) -> Optional[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM usuarios WHERE email = %s AND ativo = 1",
            (email.strip().lower(),),
        )
        return _to_dict(cur.fetchone())
    finally:
        conn.close()


def get_usuario(user_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
        return _to_dict(cur.fetchone())
    finally:
        conn.close()


def listar_usuarios_empresa(empresa_id: str, apenas_ativos: bool = True) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        q = ("SELECT id, nome, email, role, ativo, lgpd_consent_at, created_at "
             "FROM usuarios WHERE empresa_id = %s")
        params: list = [empresa_id]
        if apenas_ativos:
            q += " AND ativo = 1"
        q += " ORDER BY nome"
        cur.execute(q, params)
        return _to_dicts(cur.fetchall())
    finally:
        conn.close()


def desativar_usuario(user_id: str, empresa_id: Optional[str] = None) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            if empresa_id:
                cur.execute(
                    "UPDATE usuarios SET ativo = 0 WHERE id = %s AND empresa_id = %s",
                    (user_id, empresa_id),
                )
            else:
                cur.execute("UPDATE usuarios SET ativo = 0 WHERE id = %s", (user_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def reativar_usuario(user_id: str, empresa_id: Optional[str] = None) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            if empresa_id:
                cur.execute(
                    "UPDATE usuarios SET ativo = 1 WHERE id = %s AND empresa_id = %s",
                    (user_id, empresa_id),
                )
            else:
                cur.execute("UPDATE usuarios SET ativo = 1 WHERE id = %s", (user_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def atualizar_usuario(user_id: str, campos: dict) -> bool:
    permitidos = {"nome", "email", "role"}
    updates = {k: v for k, v in campos.items() if k in permitidos}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE usuarios SET {set_clause} WHERE id = %s", values)
            return cur.rowcount > 0
    finally:
        conn.close()


def alterar_senha_hash(user_id: str, new_hash: str) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("UPDATE usuarios SET senha_hash = %s WHERE id = %s", (new_hash, user_id))
            return cur.rowcount > 0
    finally:
        conn.close()


def apagar_dados_usuario(user_id: str) -> bool:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE usuarios SET nome = '[dados removidos]', "
                "email = 'removido_' || id || '@apagado.local', "
                "senha_hash = '', ativo = 0 WHERE id = %s",
                (user_id,),
            )
            return True
    except Exception:
        return False
    finally:
        conn.close()


def email_existe(email: str) -> bool:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM usuarios WHERE email = %s", (email.strip().lower(),))
        return cur.fetchone() is not None
    finally:
        conn.close()


# ── Sessoes ───────────────────────────────────────────────────────────────────

def salvar_sessao(
    empresa_id: str,
    usuario_id: str,
    tema: str,
    results_json: str,
) -> int:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sessoes (empresa_id, usuario_id, tema, results_json) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (empresa_id, usuario_id, tema, results_json),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def get_ultima_sessao(empresa_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM sessoes WHERE empresa_id = %s ORDER BY timestamp DESC LIMIT 1",
            (empresa_id,),
        )
        return _to_dict(cur.fetchone())
    finally:
        conn.close()


def listar_sessoes(empresa_id: str, limit: int = 20) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, tema, timestamp, usuario_id FROM sessoes "
            "WHERE empresa_id = %s ORDER BY timestamp DESC LIMIT %s",
            (empresa_id, limit),
        )
        return _to_dicts(cur.fetchall())
    finally:
        conn.close()


def get_sessao(sessao_id: int, empresa_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM sessoes WHERE id = %s AND empresa_id = %s",
            (sessao_id, empresa_id),
        )
        return _to_dict(cur.fetchone())
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
    try:
        conn = _connect()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO audit_log (usuario_id, empresa_id, acao, detalhes, ip) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (usuario_id, empresa_id, acao, detalhes, ip),
                )
        finally:
            conn.close()
    except Exception:
        pass


def listar_audit(empresa_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if empresa_id:
            cur.execute(
                "SELECT * FROM audit_log WHERE empresa_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (empresa_id, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return _to_dicts(cur.fetchall())
    finally:
        conn.close()
