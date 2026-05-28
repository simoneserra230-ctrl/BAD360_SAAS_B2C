@echo off
chcp 65001 >nul
title BAD360.ai — Hospitality AI Platform v4.0

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║       BAD360.ai  —  Hospitality AI Platform  v4.0       ║
echo  ║       Suite Modulare · 19 Moduli · FastAPI Backend      ║
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
    echo  [!] Senza la chiave i moduli AI non funzioneranno.
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
    echo  [SETUP] Installo dipendenze (prima volta, attendere ~2 minuti)...
    pip install -r requirements.txt --quiet
    echo  [OK] Dipendenze installate.
)

REM ── Aggiorna dipendenze se necessario ─────────────────────────────
echo  [OK] Controllo dipendenze...
pip install -r requirements.txt --quiet 2>nul

REM ── Verifica BAD360_SPLIT ──────────────────────────────────────────
IF NOT EXIST "BAD360_SPLIT\index.html" (
    echo  [ERRORE] Cartella BAD360_SPLIT non trovata o index.html mancante.
    echo  Assicurati di eseguire questo .bat dalla cartella BAD360.SKILLSOLUTIONS.COM
    pause
    exit /b 1
)

REM ── Apri browser automaticamente ─────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║  URL:       http://localhost:8000                        ║
echo  ║  API Docs:  http://localhost:8000/api/docs               ║
echo  ║  Premi CTRL+C per fermare il server                      ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

REM ── Avvia FastAPI ─────────────────────────────────────────────────
set PYTHONUTF8=1
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
