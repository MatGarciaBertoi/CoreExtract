@echo off
:: ══════════════════════════════════════════════════════════
::  CoreExtract — Inicialização no Windows
::  Execute: clique duplo em run.bat ou rode no terminal
:: ══════════════════════════════════════════════════════════

title CoreExtract

:: Verifica se o .env existe
if not exist ".env" (
    echo [AVISO] Arquivo .env nao encontrado.
    echo Copiando .env.example para .env...
    copy .env.example .env
    echo.
    echo IMPORTANTE: Edite o arquivo .env e adicione sua GROQ_API_KEY antes de continuar.
    echo Abra o .env com: notepad .env
    pause
    exit /b 1
)

:: Verifica se o ambiente virtual existe, senão instala as dependências
if not exist "venv\" (
    echo [1/3] Criando ambiente virtual Python...
    python -m venv venv
)

echo [2/3] Ativando ambiente e instalando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

echo [3/3] Iniciando CoreExtract em http://localhost:8080
echo.
echo  Acesse no navegador: http://localhost:8080
echo  Pressione Ctrl+C para parar
echo.

python main.py
