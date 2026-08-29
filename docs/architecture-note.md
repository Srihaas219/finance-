# LoanTrust Copilot — Architecture Note

**Intain Campus FinTech Challenge 2026 · Full Stack Track**
Date: 2026-08-28 · Version: 1.0 (complete, demo-ready)

---

## 1. Purpose and Scope

LoanTrust Copilot is a loan-data verification console that ingests messy CSV loan tape files, normalises and validates them against a configurable rule set, raises exceptions for human review, provides advisory AI assistance, produces immutable verified records with a full audit trail, and exposes a consumer-facing traceability API.

The system supports three distinct roles — **Data Operator**, **Reviewer**, and **Data Consumer** — each with a dedicated dashboard and scoped API access.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Browser SPA  (React 18 + Vite + TypeScript + Tailwind)  │
│  OperatorDashboard · ReviewerDashboard · ConsumerDashboard│
└─────────────────────────┬────────────────────────────────┘
                          │ HTTPS / JSON  (JWT Bearer)
                          ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI Backend  (Python 3.11, modular monolith)        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │Ingestion │ │Validation│ │  Review  │ │Verification│  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │  AI/LLM  │ │  Audit   │ │  Export  │ │   Auth     │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘  │
└─────────────────────────┬────────────────────────────────┘
                          │ SQLAlchemy ORM + Alembic
                          ▼
┌──────────────────────────────────────────────────────────┐
│  PostgreSQL (Docker Compose)  ·  SQLite (tests / E2E)    │
└──────────────────────────────────────────────────────────┘
```

**Infrastructure:** Docker Compose (`db` + `api` + `web`). Backend venv with `uv`. Migrations via Alembic (8 migrations, `0001_initial` → `0008_servicer`). CI: GitHub Actions (ruff lint + migration smoke + pytest).

---

## 3. Data Flow

```
CSV upload (loan_tape / servicer_update)
    │
    ▼ [Ingestion module]
Raw records preserved immutably (raw_records)
    │  stream-parse, batched FK-ordered flush, SHA-256 file_hash
    ▼ [Normalisation — pure, per-field]
Canonical loans (loans) + field_provenance JSON + normalization_status
    │
    ▼ [Validation engine — 15 rule classes, deterministic]
LoanException rows (loan_pk, rule_id, field, severity, status=open)
    │
    ▼ [Reviewer workbench]
Advisory AI (request_ai → AIRecommendation, advisory=True)  ─┐
Human decision (edit_field / ignore / approve / reject)       │ Human is authoritative
Exception resolved / loan decision recorded                   │
    │                                                         │
    ▼ [Verification service]                                  │
VerifiedLoan (snapshot, SHA-256 record_hash, version) ◄───────┘
    │  immutable; V2 supersedes V1, old versions preserved
    ▼ [Consumer API / Trace / Export]
Consumer dashboard: verified list · hash · 8-step traceability chain · CSV/JSON export
```

---

## 4. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| AI provider abstraction | `AIProvider` ABC + `MockAIProvider` default | Demo runs zero-credential, offline, deterministically. Real provider added without touching callers. |
| AI is advisory only | `AIRecommendation` rows; humans apply via `edit_field` | Prevents AI from silently mutating canonical data (ADR-003/017). |
| Immutable raw records | `raw_records` written once, never updated | Full source evidence always available for audit. |
| Immutable verified records | `VerifiedLoan.record_hash` (SHA-256); supersede-not-update | Record integrity guarantee survable across DB snapshots. |
| Optimistic concurrency | `exception.version` checked on review actions | Stale concurrent writes are rejected with HTTP 409. |
| Append-only audit log | `audit_events` emitted inside every mutation transaction | Audit trail cannot be rewritten. |
| Per-field provenance | `field_provenance` JSON column on `loans` | Every canonical value is traceable to raw source column + transformation. |
| Validation rule config | `validation_rules.json` (seed) + 15 pure rule functions | Rules are testable in isolation; config-driven thresholds. |
| NL rule generation | AI generates advisory JSON rule skeleton from natural language | Humans must review and manually import; never auto-applied. |

---

## 5. Module Inventory

| Module | Key files | Responsibility |
|--------|-----------|----------------|
| `core/` | `config`, `db`, `security`, `hashing`, `ids`, `context` | Settings, DB sessions, JWT, SHA-256, request-ID middleware |
| `ingestion/` | `normalize.py`, `service.py`, `routes_ingestion.py` | CSV parse → raw preserve → normalise → loan upsert |
| `validation/` | `config.py`, `rules.py`, `engine.py`, `service.py` | 15 deterministic rule classes, exception creation |
| `review/` | `service.py`, `routes_review.py` | Exception state machine, field edit, loan decision |
| `ai/` | `provider.py`, `service.py`, `routes_ai.py` | Provider abstraction, Mock, 6 AI kinds, NL rule gen, audit log |
| `verification/` | `service.py`, `trace.py`, `routes_verification.py` | Immutable verified record, SHA-256 hash, traceability |
| `audit/` | `service.py` | Append-only audit event builder |
| `models/` | 10 ORM models | SQLAlchemy mapped classes + Alembic migrations |
| `api/` | `routes_dashboard`, `routes_ai`, `routes_ingestion` | Role-gated FastAPI routers, Pydantic schemas |

---

## 6. Security and Role Boundaries

- **JWT authentication**: HS256 signed tokens, 8-hour expiry, role claim embedded.
- **`require_role` dependency**: Every API router checks the token role before any DB access.
- **Role matrix**:

| Capability | Operator | Reviewer | Consumer |
|------------|----------|----------|----------|
| Upload loan tape / servicer feed | ✓ | — | — |
| Run validation | ✓ | — | — |
| View exceptions / AI assistance | — | ✓ | — |
| Edit fields / make loan decisions | — | ✓ | — |
| Verify loans | — | ✓ | — |
| Browse verified records / trace | — | — | ✓ |
| Export (CSV/JSON) | — | — | ✓ |

- AI endpoints are reviewer-only; AI output is never applied without a human action.
- Verified records are immutable after creation; the hash is reproducible.

---

## 7. Test Coverage

| Layer | Count |
|-------|-------|
| Backend unit + integration tests (`pytest`) | **132** |
| Browser E2E (Playwright, full Operator→Reviewer→Consumer journey) | **1** |
| Ruff lint | clean |
| Ground-truth reconciliation (252-row ledger, 0 false negatives) | pass |

---

## 8. AI Feature Summary

Six AI kinds, all served by the deterministic `MockAIProvider` (zero credentials, offline):

| Kind | Purpose | Advisory |
|------|---------|----------|
| `explain` | Explain why a rule fired | Yes |
| `suggest_correction` | Suggest a field value correction | Yes (human applies) |
| `resolve_conflict` | Recommend value from conflicting sources | Yes (human applies) |
| `reviewer_note` | Draft a reviewer note | Yes |
| `classify_severity` | Cross-check deterministic severity | Yes (engine is authoritative) |
| `nl_rule_generation` | Generate rule skeleton from natural language | Yes (manual import required) |

Every AI call is logged in `ai_audit_logs` with provider, model, prompt hash, latency, and degraded flag. A real provider (e.g., Anthropic Claude) can be plugged in via `AI_PROVIDER=anthropic` env var without touching business logic.
