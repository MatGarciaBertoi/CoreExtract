@echo off
:: ══════════════════════════════════════════════════════════════════
::  BTExtract — Inicialização no Windows
::  Inicia: API (8080) + Dashboard Streamlit (8081)
::  Duplo clique ou: run.bat
:: ══════════════════════════════════════════════════════════════════

title BTExtract · Iniciando...
cd /d "%~dp0"

:: ── Verifica .env ─────────────────────────────────────────────────
if not exist ".env" (
    echo.
    echo  [AVISO] Arquivo .env nao encontrado.
    if exist ".env.example" (
        copy .env.example .env >nul
        echo  Criado .env a partir de .env.example
        echo.
        echo  IMPORTANTE: Abra o .env e adicione sua chave Gemini:
        echo     notepad .env
        echo.
    ) else (
        echo  Crie o arquivo .env com a variavel GEMINI_API_KEY.
    )
    pause
    exit /b 1
)

:: ── Cria venv se não existir ──────────────────────────────────────
if not exist "venv\" (
    echo.
    echo  [1/3] Criando ambiente virtual Python...
    python -m venv venv
    if errorlevel 1 (
        echo  [ERRO] Python nao encontrado. Instale em https://python.org
        pause
        exit /b 1
    )
)

:: ── Instala / atualiza dependências ──────────────────────────────
echo.
echo  [2/3] Verificando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERRO] Falha ao instalar dependencias. Verifique requirements.txt
    pause
    exit /b 1
)

:: ── Inicia o launcher (FastAPI + Streamlit) ───────────────────────
echo.
echo  [3/3] Iniciando BTExtract...
echo.
echo  ┌─────────────────────────────────────────────┐
echo  │  BTExtract  →  http://localhost:8080       │
echo  │  Dashboard    →  http://localhost:8081       │
echo  │                                              │
echo  │  Pressione Ctrl+C para encerrar             │
echo  └─────────────────────────────────────────────┘
echo.

python launcher.py

:: Se o launcher encerrar com erro, mantém janela aberta
if errorlevel 1 (
    echo.
    echo  [ERRO] O BTExtract encerrou com erro. Veja a mensagem acima.
    pause
)
