"""
SQLite-based key-value store for CoreExtract application settings.

Database location: C:/CoreExtract/coreextract.db
Thread-safe: yes (module-level lock).

Keys managed:
    GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_FROM_NAME, GEMINI_MODEL, GEMINI_API_KEY

On first run, migrates existing values from the .env file so the user's current
configuration is not lost.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
_DB_PATH  = Path(__file__).parent / "coreextract.db"
_ENV_PATH = Path(__file__).parent / ".env"

# Keys that this module manages (all others remain .env-only)
_MANAGED_KEYS: tuple[str, ...] = (
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "EMAIL_FROM_NAME",
    "GEMINI_MODEL",
    "GEMINI_API_KEY",
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
