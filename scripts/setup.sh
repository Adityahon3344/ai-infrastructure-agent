#!/usr/bin/env bash
# One-shot setup for Linux/macOS.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Setting up backend"
cd "$ROOT/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
mkdir -p data

echo "==> Setting up frontend"
cd "$ROOT/frontend"
npm install

echo ""
echo "Setup complete."
echo "Backend:  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
echo "Frontend: cd frontend && npm run dev"
