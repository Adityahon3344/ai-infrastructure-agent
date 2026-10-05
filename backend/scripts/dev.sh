#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
python -m venv .venv 2>/dev/null || true
source .venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
