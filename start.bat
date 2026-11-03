@echo off
REM BookMind launcher (Windows): installs dependencies on first run, then starts backend + frontend.
REM   start.bat lan   also lets phones on the same Wi-Fi open (and install) BookMind.
setlocal
cd /d "%~dp0"
set MODE=%~1

if not exist backend\.env (
  copy backend\.env.example backend\.env >nul
  echo Created backend\.env from the example. Edit it ^(DATABASE_URL; LLM_PROVIDER/LLM_MODEL^) and run start.bat again.
  notepad backend\.env
  exit /b 1
)

if not exist backend\.venv\Scripts\python.exe (
  echo [1/4] Creating Python virtual environment...
  python -m venv backend\.venv || (echo Python 3.11+ is required: https://www.python.org/downloads/ & exit /b 1)
)
echo [2/4] Checking Python dependencies...
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt || exit /b 1

echo [3/4] Preparing database...
pushd backend
.venv\Scripts\python.exe scripts\setup_db.py || (popd & exit /b 1)
popd

if not exist frontend\node_modules (
  echo [4/4] Installing frontend dependencies...
  pushd frontend
  call npm install --no-fund --no-audit || (popd & exit /b 1)
  popd
)

REM Warn (don't stop) if the AI model isn't ready, e.g. Ollama not running or the model not pulled.
backend\.venv\Scripts\python.exe backend\scripts\check_llm.py

if /i "%MODE%"=="lan" goto lan

echo Starting backend on http://127.0.0.1:8000 and frontend on http://localhost:5173 ...
start "BookMind backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe run.py"
start "BookMind frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 4 >nul
start http://localhost:5173
exit /b 0

:lan
REM One address for phones on the same Wi-Fi: the backend serves the built app.
echo Building the app for phones...
pushd frontend
call npm run build || (popd & exit /b 1)
popd
backend\.venv\Scripts\python.exe backend\scripts\lan_info.py
set HOST=0.0.0.0
cd /d "%~dp0backend"
.venv\Scripts\python.exe run.py
