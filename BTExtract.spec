# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — BTExtract v2.0
Gera uma pasta dist/BTExtract/ com o executável e todos os assets.
Build: pyinstaller BTExtract.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821  (variável injetada pelo PyInstaller)

# ── Assets que precisam ser copiados para dentro do bundle ──────────────────
datas = [
    # (origem,              destino dentro do bundle)
    (str(ROOT / "templates"), "templates"),   # frontend.html, email_base.html
    # dashboard.py NÃO entra no bundle — é copiado pelo build_installer.bat
    # diretamente para dist/BTExtract/ (precisa ser um arquivo normal, não embutido)
]

# ── Hidden imports que o PyInstaller não detecta automaticamente ─────────────
hidden_imports = [
    # FastAPI / Starlette
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    # Pydantic
    "pydantic",
    "pydantic.v1",
    # Google Gemini
    "google.generativeai",
    "google.ai.generativelanguage_v1beta",
    # python-dotenv
    "dotenv",
    # openpyxl
    "openpyxl",
    "openpyxl.styles",
    "openpyxl.chart",
    "openpyxl.utils",
    # python-docx
    "docx",
    # Extratores de PDF
    "pypdf",
    "pdfplumber",
    # Email
    "smtplib",
    "ssl",
    "email",
    "email.mime",
    "email.mime.multipart",
    "email.mime.text",
    "email.mime.base",
    # SQLite (built-in, mas garantindo)
    "sqlite3",
    # Outros  (Streamlit/Plotly/Pandas NÃO entram aqui — rodam via Python embutido)
    "multipart",
    "python_multipart",
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    "httpx",
    "h11",
]

# ── Bloco de análise ─────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "launcher.py")],          # ponto de entrada
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",          # excluído por padrão — incluído só se pystray estiver
        "pystray",
        "IPython",
        "jupyter",
        "notebook",
        "test",
        "tests",
        "_pytest",
        "pytest",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BTExtract",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # True = mostra console (útil para debug inicial)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BTExtract",     # → dist/BTExtract/
)
