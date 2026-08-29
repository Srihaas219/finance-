# DevOps Plan

> Target: `docker compose up --build` boots the whole system; `docker compose down -v` gives a clean reset. Deterministic seed + demo-reset restore the canonical dataset.

## Environments

| Env | Purpose | AI provider | DB | Notes |
|---|---|---|---|---|
| LOCAL | dev | Mock (default) | Docker Postgres | hot reload FE/BE |
| TEST / CI | automated tests | Mock (forced) | ephemeral Postgres (or SQLite for unit) | no network to real AI |
| DEMO / PROD | judging | Mock default; Anthropic if key set | Docker Postgres w/ seed | `demo-reset` before recording |

## Docker Compose services
- `db` — postgres:16, volume `pgdata`, healthcheck `pg_isready`.
- `api` — FastAPI (uvicorn). Depends on `db` healthy. Runs Alembic migrations on entrypoint, then seeds if empty. Exposes `/healthz`, `/readyz`.
- `web` — Vite build served by nginx (prod) or `vite dev` (local). Talks to `api` via `VITE_API_URL`.
- (later) `redis` + `worker` — only when Scaling Stage 2 triggers (see scaling-strategy).

## Environment variables (`.env.example`, real `.env` gitignored)
```
# Backend
DATABASE_URL=postgresql+psycopg://loantrust:loantrust@db:5432/loantrust
JWT_SECRET=change-me-in-prod
AI_PROVIDER=mock            # mock | anthropic
ANTHROPIC_API_KEY=          # only if AI_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-opus-4-8
AI_TIMEOUT_SECONDS=20
CORS_ORIGINS=http://localhost:5173
LOG_LEVEL=info
RULESET_PATH=/app/seed/validation_rules.json
# Frontend
VITE_API_URL=http://localhost:8000
```

## Secrets policy
- No secrets in git. `.env` + `frontend/.env` gitignored; only `.env.example` committed.
- Real AI key optional — absence must not break anything (falls back to Mock).
- JWT secret injected via env; rotate for any real deployment (out of scope but noted).

## Database init, migrations, seed
- **Migrations:** Alembic. Entry script: `alembic upgrade head` before app start. `readyz` fails until schema present.
- **Seed data (deterministic):** load organizer package into DB —
  `loan_tape.csv`, `servicer_update.csv`, `document_manifest.csv`, `validation_rules.json`, `users.json`, `expected_exception_sample.csv`. Fixed IDs/timestamps so hashes and demo are reproducible.
- **Seed command:** `make seed` / `python -m app.seed`. Idempotent (skip if already seeded).

## Demo reset workflow
- `make demo-reset` → truncate operational + evidence + output tables, re-run seed → identical starting state every rehearsal/recording.
- Full nuke: `docker compose down -v && docker compose up --build`.

## Health & readiness
- `GET /healthz` — process alive (no deps). For container liveness.
- `GET /readyz` — DB reachable + migrations at head + ruleset loaded. For dependency ordering and LB.

## Logging & error tracking
- Structured JSON logs (request id, actor, route, latency). `LOG_LEVEL` from env.
- **Implemented (Loop 3):** `request_context` middleware assigns/propagates `X-Request-ID`, binds it to a contextvar surfaced on every JSON log line, and emits one structured access log per request (`method`, `path`, `status`, `duration_ms`). Response carries `X-Request-ID` back.
- Error tracking behind an abstraction (`core/telemetry.py`): no-op locally, pluggable (e.g. Sentry) in prod. No hard dependency. (telemetry seam added when first needed.)

## Health & readiness (implemented)
- `GET /healthz` **and alias `GET /health`** — liveness, no deps.
- `GET /readyz` **and alias `GET /ready`** — DB reachable; returns 503 when not. No fake checks.

## CI pipeline (GitHub Actions)
**Implemented (Loop 3), `.github/workflows/ci.yml`:**
1. Backend: install → **`ruff check`** → **clean-DB migration check (`alembic upgrade head`)** → **`pytest`** (Mock AI forced, SQLite).
2. Frontend: install → **typecheck + build** (`npm run build`).

**Planned (later slices):** coverage gate on validation + hashing + AI-boundary tests; import-linter module-boundary contract (once modules exist); optional nightly Playwright 3-role e2e; optional Docker-build verification. `eslint` deferred — TypeScript `--noEmit` already gates the frontend; add eslint only if style drift appears (avoids CI churn now).
No deploy step required (local-runnable satisfies PS); optional single-VM/Render/Fly deploy documented in README if time permits.

## Backup assumptions
Synthetic, reproducible-from-seed data → no backup needed for the competition. Noted as out of scope for production.

## One-command run (README target)
```
cp .env.example .env
docker compose up --build          # db + api(migrate+seed) + web
# open http://localhost:5173  — login with seeded creds (see README)
docker compose down -v             # clean reset
```
