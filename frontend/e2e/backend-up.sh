#!/usr/bin/env bash
# Start the backend for browser E2E against a fresh, deterministic SQLite DB, seeded with
# users + the demo dataset (loan tape + servicer feed + validation). Used by Playwright's
# webServer. Not for production.
set -e
cd "$(dirname "$0")/../../backend"

export DATABASE_URL="sqlite:///./e2e.db"
export JWT_SECRET="e2e-secret"
export AI_PROVIDER="mock"
export CORS_ORIGINS="http://localhost:5173,http://localhost:4173"

rm -f e2e.db
. .venv/bin/activate
alembic upgrade head
python -m app.seed
python -m app.demo_seed
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
