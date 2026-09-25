@echo off
cd /d "%~dp0"

REM ------------------------------------------------------------------
REM BiliNote local launcher
REM   Backend : FastAPI on 8483 (uv-managed venv: backend/.venv)
REM   Frontend: Vite on 3015 (BillNote_frontend)
REM NOTE: keep this file ASCII-only. cmd.exe reads .bat as ANSI/GBK,
REM       UTF-8 Chinese comments get garbled and may run as commands.
REM ------------------------------------------------------------------

REM --- 1. Free ports 8483 (backend) / 3015 (frontend) if occupied ---
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8483,3015 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

REM --- 2. Check backend venv exists ---
if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] backend\.venv not found. Create it first:
  echo   cd backend
  echo   uv venv --python 3.11 .venv
  echo   uv pip install -r requirements.txt
  echo   uv pip install "setuptools<81"
  pause
  exit /b 1
)

REM --- 3. Start backend + frontend ---
start "Backend" powershell -NoExit -Command "cd backend; .\.venv\Scripts\python.exe main.py"
start "Frontend" powershell -NoExit -Command "cd BillNote_frontend; npm run dev"

REM --- 4. Open browser ---
start http://localhost:3015/

