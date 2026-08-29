# LoanTrust Copilot — Architecture

> Status: FOUNDATION (Loop 1). No business logic implemented yet.
> Source of truth for scope: `docs/reference/problem-statement-extracted.txt` (Intain Full Stack Track).

## 1. System Context

```
                         ┌─────────────────────────────────────────┐
   Data Operator ─────►  │                                         │
   Reviewer      ─────►  │        LoanTrust Copilot (SPA)          │  ◄── AI Provider
   Data Consumer ─────►  │      React + Vite + TS + TanStack       │      (Anthropic | Mock)
                         └──────────────────┬──────────────────────┘
                                            │ HTTPS / JSON
                                            ▼
                         ┌─────────────────────────────────────────┐
                         │        Backend API (FastAPI)            │
                         │  ingestion · validation · exceptions ·  │
                         │  review · AI orchestration · verify ·   │
                         │  audit · export                         │
                         └──────────────────┬──────────────────────┘
                                            │ SQLAlchemy
                                            ▼
                         ┌─────────────────────────────────────────┐
                         │   PostgreSQL   +   Object storage       │
                         │   (relational) │   (raw source files)   │
                         └─────────────────────────────────────────┘
```

**Actors**
- **Data Operator** — uploads loan tapes, monitors imports and validation summaries.
- **Reviewer** — works the exception queue, requests/uses AI, makes approve/reject/correct decisions.
- **Data Consumer** — reads verified records, quality metrics, audit trail; exports.
- **AI Provider** — pluggable. Real (Anthropic) or deterministic **Mock** (default for tests/demo).

**External dependency posture:** The app MUST remain fully usable if the AI provider is unavailable (RA-BR-9). AI is an *assistant*, never a gate.

## 2. Container / Component Architecture — Modular Monolith

Single deployable backend, internally partitioned into modules with explicit boundaries. See ADR-001.

```
backend/app/
  core/           # config, db session, security, hashing, ids, logging
  ingestion/      # CSV upload, raw preservation, normalization, lineage
  validation/     # deterministic rule engine (source of truth)
  exceptions/     # exception queue, filtering, search
  review/         # comments, field edits, approve/reject/correct, decision log
  ai/             # provider abstraction (real + mock), orchestration, ai_audit
  verification/   # verified snapshots, versioning, record hashing
  audit/          # append-only audit events
  api/            # FastAPI routers (thin) -> call module services
  consumer/       # verified-records read API + export
```

**Layering rule (enforced by review, later by import-linter):**
`api → module services → core`. Modules communicate through service functions and the DB, **not** by reaching into each other's internals. `validation` never imports `ai`. `ai` never writes canonical loan fields.

**Frontend**
```
frontend/src/
  app/            # router, providers (TanStack Query, auth)
  features/
    operator/     # upload, import history, validation summary
    reviewer/     # exception queue, loan detail, AI panel, decisions
    consumer/     # verified records, quality score, audit viewer, export
  components/ui/  # shadcn/ui primitives
  lib/            # api client, types (generated from OpenAPI), auth
```

## 3. Sync vs Async Operations

Competition scale is 1k–5k rows. Default everything **synchronous** for demo determinism and simplicity (ADR-006).

| Operation | Mode | Rationale |
|---|---|---|
| CSV upload + raw store | Sync | Small files; must return an import summary immediately. |
| Normalization + validation | Sync (single txn per import) | 5k rows validate in well under a second with in-process rules. Determinism > throughput. |
| AI recommendation | Sync request, **on-demand only** | Reviewer explicitly triggers it; never auto-run on import. Timeout + fallback to Mock/degraded. |
| Verified snapshot + hash | Sync (single txn) | Must be atomic with audit event. |
| Export | Sync stream | Bounded dataset. |

**Future trigger for async:** files >100k rows, or AI batch-summary latency harming UX → introduce a task queue (see `scaling-strategy.md`). Not now.

## 4. Data Lifecycle

See `data-lifecycle.md`. Three immutability tiers:
- **L1 Evidence** (immutable): `source_files`, `raw_records` + hashes.
- **L2 Operational** (mutable workflow state): `loans`, `validation_runs`, `validation_results`, `exceptions`, `review_decisions`, `ai_recommendations`.
- **L3 Trusted output** (immutable/versioned): `verified_loans` snapshots + `record_hash`.

## 5. Loan State Machine

See `system-state-machine.md`. Every transition names the responsible role, the audit event emitted, and its transaction boundary. Verified snapshots are never mutated; corrections create a new version.

## 6. Role Access Model (RBAC)

| Capability | Operator | Reviewer | Consumer |
|---|---|---|---|
| Upload CSV / view import history | ✅ | — | — |
| View validation summary | ✅ | ✅ | ✅ (aggregate) |
| Exception queue / filter / search | read | ✅ full | — |
| Add comment / edit allowed field | — | ✅ | — |
| Request AI / accept-edit-reject AI | — | ✅ | — |
| Approve / reject / request correction | — | ✅ | — |
| Create verified record | — | ✅ (on approve) | — |
| View verified records / quality metrics | — | ✅ | ✅ |
| View audit trail | ✅ (own imports) | ✅ | ✅ |
| Export verified records | — | — | ✅ |

Enforcement: FastAPI dependency `require_role(...)` on every router. Roles seeded from `users.json`. Auth: signed JWT (demo-grade; production security is explicitly out of scope per PS §16).

## 7. AI Trust Boundaries (hard rules)

1. **Determinism is the source of truth.** Validation results and exceptions are computed only by the rule engine. AI cannot create/clear exceptions.
2. **AI never mutates canonical data.** AI output lands in `ai_recommendations` only. A human applies (or discards) any field change via the `review` module, which is what actually writes.
3. **Separation of record.** AI recommendation and human decision are distinct rows; the UI shows them side by side.
4. **Every AI call is logged** to `ai_audit_logs` with prompt, model id, provider, timestamp, latency, token/usage (where available), and a hash of the input context.
5. **Graceful degradation.** Provider error/timeout → structured "AI unavailable" response; workflow continues.
6. **Deterministic Mock provider** is the default in tests and demo, producing stable, assertable output.

## 8. Audit Architecture

Append-only `audit_events` table; no updates or deletes. Each event: `id`, `event_type`, `actor_id`/`actor_role` (or `system`/`ai`), `loan_id?`, `entity_type`, `entity_id`, `payload` (JSONB, before/after where relevant), `occurred_at`, `prev_hash`, `event_hash`. Events are written **in the same transaction** as the state change they describe (outbox-free consistency at this scale). Optional hash-chain (`event_hash = H(prev_hash || canonical(event))`) gives tamper-evidence for the traceability score. Covers all 10 PS Module F events.

## 9. Hashing Architecture

- **File hash:** SHA-256 of raw uploaded bytes → `source_files.file_hash` (dedupe + evidence).
- **Raw row hash:** SHA-256 of the canonicalized raw cells → `raw_records.row_hash` (per-row lineage).
- **Verified record hash:** SHA-256 over a **canonical JSON serialization** (sorted keys, normalized types, excluding volatile fields) of the verified snapshot → `verified_loans.record_hash`. Deterministic and reproducible; documented so a judge can recompute it.
- **Audit chain hash:** optional per §8.

Canonicalization is a single shared `core/hashing.py` function so every layer hashes identically.

## 10. Failure Handling Strategy

| Failure | Behavior |
|---|---|
| Malformed CSV / wrong schema | Reject file with row-level error report; still preserve the raw upload. |
| Partial bad rows | Import good rows; list failed rows in the summary with reasons. |
| Duplicate file upload (same hash) | Warn; do not silently re-import. |
| AI provider down/timeout | Degraded response; reviewer proceeds manually. |
| DB error mid-import | Whole import rolled back (atomic); nothing half-written. |
| Verify race (double approve) | Idempotency: version guard + unique constraint on `(loan_id, version)`. |

## 11. Scaling Strategy

Summary here; detail in `scaling-strategy.md`. Stay a modular monolith. Scale vertically + add indexes first. Extract ingestion/validation into a worker only when a concrete throughput or deployment-independence trigger fires.

## 12. DevOps Architecture

Summary here; detail in `devops-plan.md`. `docker compose up --build` brings up `db`, `api`, `web`. `docker compose down -v` resets. Deterministic seed + demo-reset script restore the canonical dataset. Health (`/healthz`) and readiness (`/readyz`) endpoints; structured JSON logging; error-tracking behind an abstraction (no-op locally).
