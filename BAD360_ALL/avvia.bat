@echo off
chcp 65001 >nul
title BAD.S Unified Platform — Avvio Server

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║       BAD.S Unified Platform  v2.0.0                    ║
echo  ║       Hospitality Intelligence ^& F^&B Management          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM ── Verifica Python ──────────────────────────────────────────────
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo  [ERRORE] Python non trovato. Installalo da https://python.org
    pause
    exit /b 1
)

REM ── Verifica .env ─────────────────────────────────────────────────
IF NOT EXIST ".env" (
    echo  [AVVISO] File .env non trovato.
    echo  Copio .env.example in .env ...
    copy ".env.example" ".env" >nul
    echo  [!] IMPORTANTE: Apri .env e inserisci la tua ANTHROPIC_API_KEY
    echo.
    notepad .env
    echo.
)

REM ── Attiva virtualenv ─────────────────────────────────────────────
IF EXIST "venv\Scripts\activate.bat" (
    echo  [OK] Attivo ambiente virtuale...
    call venv\Scripts\activate.bat
) ELSE (
    echo  [SETUP] Creo ambiente virtuale Python...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo  [SETUP] Installo dipendenze (prima volta, attendere)...
    pip install -r requirements.txt --quiet
    echo  [OK] Dipendenze installate.
)

REM ── Verifica dipendenze aggiornate ────────────────────────────────
echo  [OK] Controllo dipendenze...
pip install -r requirements.txt --quiet --upgrade 2>nul

REM ── Apri browser automaticamente ─────────────────────────────────
echo.
echo  [START] Avvio server su http://localhost:8000
echo  [INFO]  API Docs: http://localhost:8000/api/docs
echo  [INFO]  Premi CTRL+C per fermare il server
echo.
start "" "http://localhost:8000"

REM ── Avvia FastAPI ─────────────────────────────────────────────────
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
