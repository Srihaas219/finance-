# LoanTrust Copilot

AI-assisted loan data verification console — turns messy loan tapes into validated, traceable, human-reviewed, verified records. Built for the Intain Campus FinTech Challenge 2026 (Full Stack Track).

> **Status:** Complete and demo-ready. Full pipeline operational: messy CSV → raw preservation → normalization + provenance → deterministic validation (15 rule classes) → exception queue → AI-assisted review (**6 AI kinds**, optional Groq real-AI) → human decision → immutable verified records → consumer traceability + export. **153 backend tests** · 1 browser E2E · ruff clean · pip-audit 0 CVEs · npm audit 0 CVEs · Docker/Postgres verified.

## Architecture
Modular monolith: React/Vite/TS SPA → FastAPI → PostgreSQL. Deterministic validation is the source of truth; AI is advisory only and never mutates canonical data. Full design in [`docs/`](docs/README.md).

## Run with Docker (recommended)
```bash
cp .env.example .env          # optional; sensible defaults work
docker compose up --build     # db + api (migrate + seed users) + web
# Web UI:  http://localhost:8080
# API:     http://localhost:8000   (Swagger at /docs)

# Optional: populate a live, validated demo state (1000 loans + servicer feed + validation)
make demo-seed                # or: docker compose exec api python -m app.demo_seed

docker compose down -v        # clean reset
make demo-reset               # reset volumes, rebuild, and auto-populate demo data
```

### Demo flow (≤5 min)
Operator: upload `data/raw/loan_tape.csv` → upload servicer feed `servicer_update.csv` → Run validation → see exceptions.
Reviewer: open the exception queue → inspect raw vs canonical + provenance → request AI explain/suggest (or "compare sources" on a conflict) → accept/reject → approve → verify (hash).
Consumer: browse verified records → inspect traceability (raw→verified) → export CSV/JSON.
Full 5-minute script in [`docs/demo-script.md`](docs/demo-script.md). Reliability checklist in [`docs/demo-readiness.md`](docs/demo-readiness.md).

## Run locally without Docker
Backend (defaults to SQLite, Mock AI):
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload        # http://localhost:8000
```
Frontend:
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

## Dataset bootstrap
The organizer's dataset is not shipped and the public Fannie/Freddie sources are registration-gated, so the repo ships a **deterministic synthetic dataset** (PS §6 schema, all 15 PS §7 issue classes) under `data/raw/`. Regenerate or swap it:
```bash
python scripts/download_datasets.py            # generate synthetic bootstrap + profile + verify
python scripts/download_datasets.py --organizer-dir /path/to/real/package --force   # use real files
python scripts/profile_datasets.py             # -> docs/dataset-profile.md + data/manifest.json
python scripts/verify_datasets.py              # SHA-256 check vs manifest (evidence integrity)
```
Data contract: [`docs/data-contract.md`](docs/data-contract.md) · quality: [`docs/dataset-quality-report.md`](docs/dataset-quality-report.md) · mapping: [`docs/field-mapping.md`](docs/field-mapping.md) · completeness+reconciliation: [`docs/dataset-completeness.md`](docs/dataset-completeness.md).

**Prove the pipeline against ground truth** (reproducible):
```bash
python scripts/reconcile_ground_truth.py   # engine vs 252-row ledger -> 252/252, 0 false negatives
python scripts/data_quality_report.py       # machine-derived stats -> docs/dataset-quality-metrics.md
```

## Test credentials (seeded)
| Role | Email | Password |
|---|---|---|
| Data Operator | operator@loantrust.demo | operator123 |
| Reviewer | reviewer@loantrust.demo | reviewer123 |
| Data Consumer | consumer@loantrust.demo | consumer123 |

> Demo placeholders until the organizer `users.json` is provided (`backend/seed/users.json`).

## Tests
```bash
make backend-test     # pytest (153 tests: health, auth, RBAC, hashing, ingestion, validation, review, AI, Groq failover, verification, audit, E2E journey)
make frontend-build   # typecheck + production build
cd frontend && npx playwright test e2e/   # browser E2E (requires Docker running on :8000 and :8080)
```

## Environment variables
See [`.env.example`](.env.example). Key ones: `DATABASE_URL`, `JWT_SECRET`, `AI_PROVIDER` (`mock`|`groq`|`anthropic`), `ANTHROPIC_API_KEY`, `CORS_ORIGINS`, `VITE_API_URL`. The app is fully usable with `AI_PROVIDER=mock` and no external keys.

### Optional: Groq real-AI provider
Set `AI_PROVIDER=groq` and at least `GROQ_API_KEY_1` to enable the Groq provider (`llama-3.3-70b-versatile` by default). A second key (`GROQ_API_KEY_2`) enables credential failover if the first key becomes unavailable. **Groq rate limits are applied at the organisation level — rotating keys does not double your quota.** The system respects `Retry-After` headers and will not cycle keys to evade rate limits. If no key is provided, the system falls back to Mock AI automatically.

## Documentation
[`docs/`](docs/README.md) — architecture, data lifecycle, state machine, ADRs, requirements traceability, risk register, test strategy, DevOps plan, roadmap, AI development log, demo script.
