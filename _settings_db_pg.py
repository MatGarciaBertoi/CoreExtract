"""
_settings_db_pg.py — implementação PostgreSQL de settings_db.
Usado automaticamente quando DATABASE_URL está definida (deploy Vercel + Supabase).
API pública idêntica ao settings_db.py (SQLite).
"""
from __future__ import annotations

import os
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_MANAGED_KEYS: tuple[str, ...] = (
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "OUTLOOK_USER",
    "OUTLOOK_APP_PASSWORD",
    "EMAIL_FROM_NAME",
    "GEMINI_MODEL",
    "GEMINI_API_KEY",
    "EMAIL_PROVIDER",
)


def _connect():
    return psycopg2.connect(DATABASE_URL, connect_timeout=8)


def _init_from_env() -> None:
    """
    Popula settings no Supabase a partir de env vars se a tabela estiver vazia.
    Roda apenas no primeiro cold start após o deploy.
    """
    try:
        conn = _connect()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM settings")
                count = cur.fetchone()[0]
                if count > 0:
                    return
                for key in _MANAGED_KEYS:
                    val = os.environ.get(key, "")
                    if val:
                        cur.execute(
                            "INSERT INTO settings (key, value) VALUES (%s, %s) "
                            "ON CONFLICT (key) DO NOTHING",
                            (key, val),
                        )
        finally:
            conn.close()
    except Exception:
        pass


_init_from_env()


# ── Settings ──────────────────────────────────────────────────────────────────

def get(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else default
        finally:
            conn.close()
    except Exception:
        return default


def set(key: str, value: str) -> None:  # noqa: A001
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value),
            )
    finally:
        conn.close()


def get_all() -> dict[str, str]:
    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM settings")
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception:
        return {}


def set_many(data: dict[str, str]) -> None:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            for key, value in data.items():
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value),
                )
    finally:
        conn.close()


# ── Comments ──────────────────────────────────────────────────────────────────

def save_comment(filename: str, comment: str) -> None:
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO comments (filename, comment, updated_at) "
                "VALUES (%s, %s, NOW()) "
                "ON CONFLICT (filename) DO UPDATE "
                "SET comment = EXCLUDED.comment, updated_at = NOW()",
                (filename, comment),
            )
    finally:
        conn.close()


def get_comment(filename: str) -> str:
    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT comment FROM comments WHERE filename = %s", (filename,))
            row = cur.fetchone()
            return row[0] if row else ""
        finally:
            conn.close()
    except Exception:
        return ""


def delete_comments_for_files(filenames: list[str]) -> None:
    if not filenames:
        return
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            placeholders = ",".join(["%s"] * len(filenames))
            cur.execute(f"DELETE FROM comments WHERE filename IN ({placeholders})", filenames)
    finally:
        conn.close()


def get_comments_for_files(filenames: list[str]) -> dict[str, str]:
    if not filenames:
        return {}
    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            placeholders = ",".join(["%s"] * len(filenames))
            cur.execute(
                f"SELECT filename, comment FROM comments WHERE filename IN ({placeholders})",
                filenames,
            )
            result = {row[0]: row[1] for row in cur.fetchall()}
            for f in filenames:
                result.setdefault(f, "")
            return result
        finally:
            conn.close()
    except Exception:
        return {f: "" for f in filenames}
