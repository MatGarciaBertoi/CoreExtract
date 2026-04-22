"""
Configurações centralizadas do CoreExtract.
Lidas do arquivo .env na raiz do projeto (via python-dotenv).
SQLite values (via settings_db) override .env values when present.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import settings_db  # noqa: E402 — must come after load_dotenv

# ── Google AI Studio — Gemini API (gratuita) ──────────────────
# Obtenha em: https://aistudio.google.com/apikey  (1 clique com conta Google)
GEMINI_API_KEY: str = settings_db.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# Modelos disponíveis gratuitamente:
#   gemini-1.5-flash-latest  → rápido, gratuito, excelente para extração
#   gemini-1.5-pro-latest    → mais poderoso, gratuito com limite menor
GEMINI_MODEL: str = settings_db.get("GEMINI_MODEL", os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))

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
