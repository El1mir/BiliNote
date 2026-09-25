@echo off
cd /d "%~dp0"

REM 后端使用 uv 创建的 .venv。首次使用前先执行：
REM   cd backend
REM   uv venv --python 3.11 .venv
REM   uv pip install -r requirements.txt
REM   uv pip install "setuptools<81"
start "Backend" powershell -NoExit -Command "cd backend; .\.venv\Scripts\python.exe main.py"
start "Frontend" powershell -NoExit -Command "cd BillNote_frontend; npm run dev"

start http://localhost:3015/
