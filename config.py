"""
Configurações centralizadas do CoreExtract.
Lidas do arquivo .env na raiz do projeto (via python-dotenv).
SQLite values (via settings_db) override .env values when present.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

from utils.paths import ENV_PATH as _env_path_for_dotenv
load_dotenv(_env_path_for_dotenv)

import settings_db  # noqa: E402 — must come after load_dotenv
from utils.key_manager import get_managed_key, is_managed  # noqa: E402

# ── Google AI Studio — Gemini API ────────────────────────────
# Prioridade: 1) chave gerenciada (embutida no build)
#             2) chave do usuário (settings_db / .env)
_managed = get_managed_key()
GEMINI_API_KEY: str = (
    _managed
    if _managed
    else settings_db.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
)
GEMINI_MANAGED: bool = is_managed()   # exposto para o frontend ocultar o campo

GEMINI_MODEL: str = settings_db.get("GEMINI_MODEL", os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"))

# ── Servidor ──────────────────────────────────────────────────
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "8080"))
CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "*").split(",")

# ── E-mail (Gmail SMTP) ────────────────────────────────────────
GMAIL_USER: str         = settings_db.get("GMAIL_USER", os.environ.get("GMAIL_USER", ""))
GMAIL_APP_PASSWORD: str = settings_db.get("GMAIL_APP_PASSWORD", os.environ.get("GMAIL_APP_PASSWORD", ""))
EMAIL_FROM_NAME: str    = settings_db.get("EMAIL_FROM_NAME", os.environ.get("EMAIL_FROM_NAME", "CoreExtract · RH Inteligente"))

# ── Limites de upload ──────────────────────────────────────────
MAX_FILE_SIZE_MB: int      = int(os.environ.get("MAX_FILE_SIZE_MB", "10"))
MAX_FILES_PER_REQUEST: int = int(os.environ.get("MAX_FILES_PER_REQUEST", "10"))
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".docx", ".xlsx", ".xls", ".txt"}
