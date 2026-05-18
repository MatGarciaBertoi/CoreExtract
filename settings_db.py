"""
SQLite-based key-value store for BTExtract application settings.

Database location (distributed): %APPDATA%\\BTExtract\\btextract.db
Database location (dev):         <project_root>/btextract.db
Thread-safe: yes (module-level lock).

Keys managed:
    GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_FROM_NAME, GEMINI_MODEL, GEMINI_API_KEY
    OUTLOOK_USER, OUTLOOK_APP_PASSWORD, EMAIL_PROVIDER

On first run, migrates existing values from the .env file so the user's current
configuration is not lost.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

# ── Paths — resolvidos via utils.paths para suportar PyInstaller ─────────────
from utils.paths import DB_PATH as _DB_PATH, ENV_PATH as _ENV_PATH

# Keys that this module manages (all others remain .env-only)
_MANAGED_KEYS: tuple[str, ...] = (
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "OUTLOOK_USER",
    "OUTLOOK_APP_PASSWORD",
    "EMAIL_FROM_NAME",
    "GEMINI_MODEL",
    "GEMINI_API_KEY",
    "EMAIL_PROVIDER",   # "gmail" | "outlook"
)

# Thread safety
_lock = threading.Lock()


# ── Bootstrap ────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    """Return a connection to the settings database (creates file if needed)."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _read_env_dict() -> dict[str, str]:
    """Parse the .env file and return a {key: value} dictionary."""
    result: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _migrate_from_env(conn: sqlite3.Connection) -> None:
    """
    One-time migration: copy managed keys from .env into SQLite.

    Runs only when the 'settings' table is empty (i.e. first run).
    """
    row = conn.execute("SELECT COUNT(*) FROM settings").fetchone()
    if row[0] > 0:
        return  # Already has data — skip migration

    env = _read_env_dict()
    for key in _MANAGED_KEYS:
        val = env.get(key)
        if val:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, val),
            )
    conn.commit()


def _init() -> None:
    """Initialise the database (idempotent — safe to call multiple times)."""
    with _lock:
        conn = _connect()
        try:
            _ensure_table(conn)
            _migrate_from_env(conn)
        finally:
            conn.close()


# Run initialisation when the module is first imported
_init()


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str, default: str | None = None) -> str | None:
    """Return the value for *key*, or *default* if not set."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()


def set(key: str, value: str) -> None:  # noqa: A001  (shadow built-in is intentional API)
    """Insert or update a single *key* / *value* pair."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


def get_all() -> dict[str, str]:
    """Return all stored settings as a plain dictionary."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row["key"]: row["value"] for row in rows}
        finally:
            conn.close()


def set_many(data: dict[str, str]) -> None:
    """Insert or update multiple key/value pairs in a single transaction."""
    with _lock:
        conn = _connect()
        try:
            for key, value in data.items():
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            conn.commit()
        finally:
            conn.close()


# ── Comments ─────────────────────────────────────────────────────────────────

def _ensure_comments_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            filename   TEXT PRIMARY KEY,
            comment    TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _init_comments() -> None:
    with _lock:
        conn = _connect()
        try:
            _ensure_comments_table(conn)
        finally:
            conn.close()


_init_comments()


def save_comment(filename: str, comment: str) -> None:
    """Insert or update a recruiter comment for the given filename."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO comments (filename, comment, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(filename) DO UPDATE
                  SET comment = excluded.comment,
                      updated_at = excluded.updated_at
                """,
                (filename, comment),
            )
            conn.commit()
        finally:
            conn.close()


def get_comment(filename: str) -> str:
    """Return the stored comment for *filename*, or empty string if none."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT comment FROM comments WHERE filename = ?", (filename,)
            ).fetchone()
            return row["comment"] if row else ""
        finally:
            conn.close()


def delete_comments_for_files(filenames: list[str]) -> None:
    """Remove all stored comments for the given filenames (called on new analysis)."""
    if not filenames:
        return
    with _lock:
        conn = _connect()
        try:
            placeholders = ",".join("?" * len(filenames))
            conn.execute(
                f"DELETE FROM comments WHERE filename IN ({placeholders})",
                filenames,
            )
            conn.commit()
        finally:
            conn.close()


def get_comments_for_files(filenames: list[str]) -> dict[str, str]:
    """Return {filename: comment} for all given filenames."""
    if not filenames:
        return {}
    with _lock:
        conn = _connect()
        try:
            placeholders = ",".join("?" * len(filenames))
            rows = conn.execute(
                f"SELECT filename, comment FROM comments WHERE filename IN ({placeholders})",
                filenames,
            ).fetchall()
            result = {row["filename"]: row["comment"] for row in rows}
            # Fill in empty string for files with no comment
            for f in filenames:
                result.setdefault(f, "")
            return result
        finally:
            conn.close()
