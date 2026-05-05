"""
Centraliza toda a resolução de caminhos do CoreExtract.

Distingue dois cenários:
  • Rodando a partir do código-fonte (dev / run.bat)
  • Rodando como executável congelado pelo PyInstaller

Regra geral:
  - Arquivos LIDOS (templates, assets) → get_resource()   → dentro do bundle
  - Dados do USUÁRIO (db, .env)        → get_data_dir()   → AppData\\Roaming\\CoreExtract
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True quando rodando como .exe gerado pelo PyInstaller."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_app_dir() -> Path:
    """
    Diretório raiz da aplicação.
    - Frozen : sys._MEIPASS  (pasta temporária de extração do PyInstaller)
    - Source  : pasta do projeto (onde main.py está)
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # utils/paths.py está em <root>/utils/ — sobe um nível
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """
    Diretório de dados do usuário — sempre gravável.
    - Frozen : %APPDATA%\\CoreExtract\\   (ex: C:\\Users\\João\\AppData\\Roaming\\CoreExtract)
    - Source  : raiz do projeto (comportamento original — não quebra o dev)
    """
    if is_frozen():
        appdata = os.environ.get("APPDATA") or str(Path.home())
        data_dir = Path(appdata) / "CoreExtract"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return get_app_dir()


def get_install_dir() -> Path:
    """
    Diretório onde o executável está instalado (ou raiz do projeto em dev).

    Diferente de get_app_dir():
      - get_app_dir()     → sys._MEIPASS  (pasta temporária, recriada a cada launch)
      - get_install_dir() → Path(sys.executable).parent  (pasta real e estável do .exe)

    Usar para arquivos que precisam ser COMPARTILHADOS entre processos filhos
    (ex: last_session.json escrito pelo FastAPI e lido pelo Streamlit).
    """
    if is_frozen():
        return Path(sys.executable).parent
    return get_app_dir()


def get_resource(relative_path: str) -> Path:
    """
    Retorna o caminho completo de um arquivo de recurso (template, ícone, etc.)
    que foi embutido no bundle pelo PyInstaller.

    Uso:
        html = get_resource("templates/frontend.html").read_text(encoding="utf-8")
    """
    return get_app_dir() / relative_path


# Atalhos para caminhos frequentes
# CE_DB_PATH pode ser definido via env var para deploy Docker/cloud (ex: /data/coreextract.db)
_db_override = os.environ.get("CE_DB_PATH")
DB_PATH        = Path(_db_override) if _db_override else get_data_dir() / "coreextract.db"
ENV_PATH       = get_data_dir()    / ".env"
SESSION_PATH   = get_install_dir() / "last_session.json"   # compartilhado com Streamlit
FRONTEND_PATH  = get_resource("templates/frontend.html")
EMAIL_TPL_PATH = get_resource("templates/email_base.html")
