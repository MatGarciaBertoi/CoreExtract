@echo off
:: ============================================================
::  CoreExtract — Build Completo do Instalador Windows
::  Executa: pyinstaller + inno setup
::  Resultado: dist\installer\CoreExtract_Setup_v2.0.exe
:: ============================================================
title CoreExtract Build

echo.
echo ============================================================
echo   CoreExtract - Build do Instalador Windows
echo ============================================================
echo.

:: Verifica se esta na pasta correta
if not exist "main.py" (
    echo [ERRO] Execute este script a partir da pasta do CoreExtract.
    pause
    exit /b 1
)

:: Ativa o ambiente virtual
echo [1/4] Ativando ambiente virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERRO] Ambiente virtual nao encontrado. Execute: python -m venv venv
    pause
    exit /b 1
)

:: Instala/atualiza pyinstaller
echo [2/4] Verificando PyInstaller...
pip install pyinstaller --quiet --upgrade
pip install pystray pillow --quiet

:: Limpa builds anteriores
echo [3/4] Limpando builds anteriores...
if exist "dist\CoreExtract" rmdir /s /q "dist\CoreExtract"
if exist "build" rmdir /s /q "build"

:: Cria pasta de assets se nao existir (icone placeholder)
if not exist "assets" mkdir assets
if not exist "assets\icon.ico" (
    echo     [AVISO] assets\icon.ico nao encontrado - build sem icone customizado
)

:: Executa o PyInstaller
echo [4/4] Compilando com PyInstaller...
echo.
pyinstaller CoreExtract.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] PyInstaller falhou. Verifique os erros acima.
    pause
    exit /b 1
)

echo.
echo [OK] Build PyInstaller concluido!
echo      Pasta: dist\CoreExtract\

:: Verifica se Inno Setup esta instalado
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if exist %ISCC% (
    echo.
    echo [5/5] Gerando instalador com Inno Setup...
    if not exist "dist\installer" mkdir "dist\installer"
    %ISCC% installer\setup.iss
    if errorlevel 1 (
        echo [ERRO] Inno Setup falhou.
    ) else (
        echo.
        echo ============================================================
        echo   BUILD CONCLUIDO COM SUCESSO!
        echo   Instalador: dist\installer\CoreExtract_Setup_v2.0.exe
        echo ============================================================
    )
) else (
    echo.
    echo [AVISO] Inno Setup nao encontrado.
    echo         Baixe em: https://jrsoftware.org/isdl.php
    echo         Em seguida execute: iscc installer\setup.iss
    echo.
    echo ============================================================
    echo   BUILD PARCIAL CONCLUIDO
    echo   Executavel: dist\CoreExtract\CoreExtract.exe
    echo   (Para distribuir, compacte a pasta dist\CoreExtract\ em .zip)
    echo ============================================================
)

echo.
pause
