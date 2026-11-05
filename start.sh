#!/usr/bin/env bash
# BookMind launcher (macOS/Linux): installs dependencies on first run, then starts backend + frontend.
# ./start.sh --lan          also lets phones on the same Wi-Fi open (and install) BookMind.
# ./start.sh --lan --https  ...and adds a secure https:// address (needed for the offline app).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "Created backend/.env from the example. Edit it (DATABASE_URL; LLM_PROVIDER/LLM_MODEL) and run ./start.sh again."
  exit 1
fi

PY=${PYTHON:-python3}
if [ ! -x backend/.venv/bin/python ]; then
  echo "[1/4] Creating Python virtual environment..."
  "$PY" -m venv backend/.venv
fi
echo "[2/4] Checking Python dependencies..."
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

echo "[3/4] Preparing database..."
(cd backend && .venv/bin/python scripts/setup_db.py)

if [ ! -d frontend/node_modules ]; then
  echo "[4/4] Installing frontend dependencies..."
  (cd frontend && npm install --no-fund --no-audit)
fi

backend/.venv/bin/python backend/scripts/check_llm.py || true

# ./start.sh --lan : one address for phones on the same Wi-Fi (the backend serves the built app).
if [ "${1:-}" = "--lan" ]; then
  echo "Building the app for phones..."
  (cd frontend && npm run build)
  export HOST=0.0.0.0
  if [ "${2:-}" = "--https" ]; then export HTTPS=true; fi
  backend/.venv/bin/python backend/scripts/lan_info.py
  cd backend
  exec .venv/bin/python run.py
fi

(cd backend && exec .venv/bin/python run.py) &
BACK=$!
(cd frontend && exec npm run dev) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT
echo "BookMind: http://localhost:5173  (API http://127.0.0.1:8000)  — Ctrl+C to stop"
wait
