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


def get_resource(relative_path: str) -> Path:
    """
    Retorna o caminho completo de um arquivo de recurso (template, ícone, etc.)
    que foi embutido no bundle pelo PyInstaller.

    Uso:
        html = get_resource("templates/frontend.html").read_text(encoding="utf-8")
    """
    return get_app_dir() / relative_path


# Atalhos para caminhos frequentes
DB_PATH       = get_data_dir() / "coreextract.db"
ENV_PATH      = get_data_dir() / ".env"
FRONTEND_PATH = get_resource("templates/frontend.html")
EMAIL_TPL_PATH = get_resource("templates/email_base.html")
