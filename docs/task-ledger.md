# Task Ledger & Implementation Roadmap

> Numbered vertical slices. Each delivers end-to-end user value and moves the demo forward. Order optimizes for a working demo early, then depth. Nothing here is built yet (Loop 1 = design).

## Priority scope

**P0 (must have — the judged demo path)**
Ingestion + raw preservation · deterministic validation (all 15 issues) · exception queue (filter/search) · loan detail + review decisions + allowed edits · AI assistant (explain/suggest/conflict) with human accept-edit-reject + AI audit · verified immutable+hashed records · audit trail + viewer · 3 role dashboards · 8 APIs + export · runnable via compose + seed + creds.

**P1 (strong differentiators)**
Batch exception AI summary · AI reviewer notes · AI severity classification · hash-chain audit · quality-score metric · Playwright e2e · versioned re-verification (V2).

**P2 (nice to have / stretch)**
AI rule/test generation from NL · servicer public-data connector · async worker · richer analytics.

---

## Vertical slices

### Slice 0 — Foundation & Skeleton ✅ DONE (Loop 2, 2026-08-27)
- **Goal:** repo runs end-to-end with health checks, migrations, seed, empty dashboards, auth.
- **User value:** all three roles can log in and see an (empty) role dashboard.
- **Backend:** FastAPI app, `core` (config/db/security/hashing/logging), Alembic init, `/healthz` `/readyz`, JWT + `require_role`, seed from `users.json`, `AIProvider` interface + Mock stub.
- **Frontend:** Vite+TS+router+TanStack Query, login, 3 dashboard shells, OpenAPI-typed client.
- **DB:** users table + core migration; empty operational tables.
- **DevOps:** docker-compose (db/api/web), `.env.example`, entrypoint migrate+seed, CI (lint/test/build).
- **Tests:** healthz/readyz, login, RBAC matrix skeleton.
- **Acceptance:** `docker compose up --build` → login as each seeded role → see dashboard. `down -v` resets.
- **Demo value:** the "log in as X" backbone of the demo.
- **Risks:** R-05, R-20, R-21, R-23 (all addressed here).
- **VERIFIED (Loop 2):** 23 backend tests pass; frontend typechecks + builds (83 modules); `docker compose up --build` brings up db+api+web on Postgres; `/readyz` 200; all 3 roles log in; RBAC returns 403 cross-role, 401 without token; nginx SPA fallback works. Actual files: `backend/` (FastAPI app, Alembic, seed, tests), `frontend/` (Vite SPA), `docker-compose.yml`, Dockerfiles, `Makefile`, CI, `README.md`.
- **Deviations from plan:** shadcn/ui deferred — used hand-written Tailwind components for the skeleton (lighter, no generator); adopt shadcn during Slice 3/reviewer UI where richer components pay off. Local/test default DB is SQLite (portable types); Postgres only in Compose (matches test-strategy).

### Slice 1 — Ingestion + Raw Preservation ✅ DONE (2026-08-27)
- **Goal:** upload a CSV, preserve raw, normalize, show import summary with failed rows.
- **User value:** Operator uploads a messy tape and immediately sees what came in.
- **Backend:** `POST /uploads` (file hash, dedupe warn), raw_records store, normalizer, `GET /uploads/:id`, `GET /uploads`, audit events (uploaded/imported).
- **Frontend:** Operator upload screen + import summary + import history.
- **DB:** source_files, raw_records, loans (+migration).
- **Tests:** upload, raw_preserved, normalize_*, failed_rows, audit_upload/import.
- **Acceptance:** upload seed `loan_tape.csv` → N imported / M failed with reasons; raw bytes recoverable.
- **Demo value:** demo steps 2–3.
- **Risks:** R-13 (normalization ambiguity), R-30.
- **VERIFIED:** 40 backend tests (15 ingestion + 5 normalize + prior 20) green; ruff clean; migration `0002` builds on clean DB. Real `data/raw/loan_tape.csv` (1000 rows) ingested over HTTP against **Postgres**: 1000 imported / 0 failed; duplicate re-upload flagged (ADR-013); `q=L00001`→6 (5 injected dup + original); provenance traces canonical→raw cell→row#; `loan.imported` audit emitted. Operator upload UI + import history built (frontend builds clean). Entities created: source_files, raw_records, loans, audit_events.
- **Real bug found & fixed (Postgres-only):** mixed `add_all` flushed `loans` before `raw_records` → FK violation (SQLite hides it, FKs off by default). Fixed with explicit dependency-ordered batch flush; also enabled `PRAGMA foreign_keys=ON` on SQLite so tests catch this class going forward.

### Slice 2 — Deterministic Validation + Exceptions
- **Goal:** run all 15 rules, create exceptions with severity, produce summary.
- **User value:** Operator sees validation summary; corrections-needed count.
- **Backend:** config-driven rule engine (RULESET_PATH), validation_runs/results, exceptions, `GET /summary`, audit (validation.executed, exception.created).
- **Frontend:** validation summary panel on Operator dashboard.
- **DB:** validation_runs, validation_results, exceptions.
- **Tests:** all 15 golden fixtures + `expected_exception_sample.csv` golden compare; audit_validate/exception.
- **Acceptance:** seed data yields expected exception counts by type/severity.
- **Demo value:** demo step 3–4.
- **Risks:** R-11 (correctness), R-14 (dup perf), R-30.

### Slice 3 — Exception Queue + Review Decisions
- **Goal:** reviewer works the queue, opens a loan, comments, edits allowed fields, approves/rejects/requests correction.
- **User value:** the core human workflow.
- **Backend:** `GET /exceptions` (filter/search), `GET /loans` `GET /loans/:id`, `POST /loans/:id/comments`, `PATCH /loans/:id/fields` (allow-list, re-validate), `POST /loans/:id/decision`, `GET /audit/:loanId`, audit (comment/edit/decision).
- **Frontend:** Reviewer queue (filter type/severity, search id), loan detail, comment box, editable allowed fields, decision buttons, action history.
- **DB:** review_decisions; audit_events.
- **Tests:** list/filter/search, edit_field, edit_forbidden, decision_*, rbac, audit_*, state_machine_forbidden.
- **Acceptance:** reviewer filters to a severity, edits a field, re-validation updates exception, approves.
- **Demo value:** demo steps 5, 8.
- **Risks:** R-15, R-33, R-12.

### Slice 4 — AI Review Assistant (P0 subset) + AI Audit
- **Goal:** on-demand AI explain/suggest/conflict, shown separately, human accept-edit-reject, fully logged.
- **User value:** Reviewer gets help without losing control.
- **Backend:** Mock provider outputs; `POST /ai/explain|suggest|resolve-conflict`, `POST /ai/:id/apply`, `GET /ai/logs/:id`, ai_recommendations, ai_audit_logs, audit (ai.recommendation.generated, decided). Timeout+fallback.
- **Frontend:** AI panel in loan detail — request buttons, recommendation card, accept/edit/reject, prompt/model/timestamp badge.
- **DB:** ai_recommendations, ai_audit_logs.
- **Tests:** ai_explain/suggest/conflict_mock, ai_no_mutation, ai_output_schema, ai_apply_human, ai_logged, ai_metadata, degradation.
- **Acceptance:** request AI on a conflict exception → recommendation appears → edit → apply creates a review_decision (not an AI write) → both logged.
- **Demo value:** demo steps 6–7.
- **Risks:** R-03, R-10, R-40, R-42 (all core AI-trust).

### Slice 5 — Verified Records + Hashing + Consumer API/Export
- **Goal:** approve → create immutable hashed verified snapshot; consumer views/exports; audit trail viewer.
- **User value:** Consumer trusts and exports the clean dataset.
- **Backend:** `POST /loans/:id/verify` (atomic snapshot+hash+audit), `GET /verified-loans`, `GET /verified-loans/:id`, `GET /export`, quality-score in `/summary`, audit (verified.created, exported).
- **Frontend:** verify action; Consumer dashboard (verified list, quality score, verification history), verified detail with hash, audit trail viewer, export button.
- **DB:** verified_loans.
- **Tests:** verify_snapshot, record_hash_reproducible, verify_atomic, verified_immutable, verified_fields, export, audit_verified/export.
- **Acceptance:** approve a loan → verified V1 with reproducible hash → consumer exports → audit shows full chain.
- **Demo value:** demo steps 9–13.
- **Risks:** R-02, R-11, R-12.

### Slice 6 — AI Depth + Re-verification + Polish (P1)
- **Goal:** batch summary, reviewer notes, severity classify; V2 re-verification; UI polish; Playwright e2e; hash-chain.
- **Tests:** batch_summary, note, severity mocks; reverification (V2 supersedes V1); e2e full flow.
- **Demo value:** wow factors + honest-limitations depth.

### Slice 7 — Stretch (P2)
AI rule/test generation from NL; public-data connector; async worker if triggered.

---

## Entity Contract Review (Phase 1 — decision before implementation)
Planned entities vs build timing, grounded in the real data shape (3 files joined on `loan_id`):

| Entity | Decision | Backing evidence / when |
|---|---|---|
| SourceFile | BUILD NOW (Slice 1) | one row per uploaded file; file_hash, duplicate_of (ADR-013) |
| RawRecord | BUILD NOW (Slice 1) | one row per CSV line; raw_payload + row_hash (immutable evidence) |
| Import | MERGE into SourceFile | a "import" == a SourceFile upload event; separate table NOT REQUIRED yet |
| CanonicalLoan (`loans`) | BUILD NOW (Slice 1) | normalized 21 fields + status |
| LoanFieldProvenance | BUILD LATER (Slice 5) | needed for per-field trace; can derive from raw_record+decisions until then. Start lightweight (JSON on snapshot), promote to table only if queries need it |
| ValidationRun | BUILD LATER (Slice 2) | ruleset_version stamp; run guard (ADR-014) |
| ValidationResult | BUILD LATER (Slice 2) | per-rule pass/fail |
| Exception | BUILD LATER (Slice 2) | unique (loan_id, rule_id) upsert |
| ReviewDecision | BUILD LATER (Slice 3) | approve/reject/correct/comment/edit as one decision log |
| ReviewerComment | MERGE into ReviewDecision (action=comment) | separate table NOT REQUIRED |
| FieldCorrection | MERGE into ReviewDecision (action=edit_field) | separate table NOT REQUIRED |
| AIRecommendation | BUILD LATER (Slice 4) | advisory, separate from decisions |
| VerifiedLoanVersion | BUILD LATER (Slice 5) | immutable snapshot + record_hash + version |
| AuditEvent | BUILD NOW (Slice 1, minimal) | append-only; used from first upload |

Net: Slice 1 creates `source_files`, `raw_records`, `loans`, `audit_events`. Comment/correction/import folded into existing entities (avoid inventing tables). Provenance starts as snapshot JSON, promoted only if needed — avoids premature modeling.

## Loop status
- **Loop 1: COMPLETE** — Phase A repo intelligence, Phase B architecture docs, Phase C roadmap, Phase D risk register. No business logic written.
- **Loop 2: COMPLETE (2026-08-27)** — Slice 0 Foundation & Skeleton implemented and verified end-to-end (see above).
- **Loop 3: COMPLETE (2026-08-27)** — Scale/reliability/devops analysis. Implemented NOW (verified): request-id + structured access logging, `/health`+`/ready` aliases, CI hardened (ruff lint + clean-DB migration check). 25 tests green, ruff clean. Documented as design: reliability scenarios S1–S6 → ADR-012…018; scaling roadmap + "10× bottleneck = sync import" in scaling-strategy. Deliberately did NOT build queue/worker/k8s (no measured trigger).
  - **Design constraints Slice 1 MUST honor** (from ADR-012/013): stream-parse the CSV; batched bulk inserts (batch 1,000); compute `file_hash`; on duplicate hash create a new `source_files` row with `duplicate_of` + reuse raw evidence + flag `duplicate` in the summary; wrap import in one transaction.
- **Phase 1 / Dataset Intelligence: COMPLETE (2026-08-27)** — no organizer dataset available (real sources gated); built deterministic synthetic bootstrap (1,000 loans, 252 seeded exceptions across all 15 classes), profiling/verify scripts, `data/manifest.json`, golden fixtures, and full data contract (`data-contract.md`, `field-mapping.md`, `dataset-quality-report.md`, `dataset-profile.md`). No ingestion/validation/UI built (per stop condition). Entity contract reviewed (above).
- **Slice 1: COMPLETE (2026-08-27)** — see Slice 1 entry above; verified end-to-end on Postgres.
- **Phase 3 (Normalization & Field Provenance): COMPLETE (2026-08-27)** — normalization + CanonicalLoan already existed (Slice 1); this loop added **per-field provenance** (`field_provenance` JSON + `normalization_status` column, migration `0003`, ADR-020), `normalize_row_full()` emitting `{field,raw_value,transformation,canonical_value,status(empty|ok|coerced|failed|review)}` for all 21 fields, `GET /loans?attention=true` filter + `issue_fields` in list + `field_provenance` in detail, operator `needs_attention` count + "Records needing attention" UI table. **57 tests** (10 new provenance: covers-all-fields/currency/date/null/invalid/whitespace/case/rate-review/repeatability/status). Verified on Postgres: 1000 imported, needs_attention=7, lineage e.g. L00041 `origination_date '13/45/2021' → None [failed]`. Chose embedded JSON over a per-field table (ADR-020) to protect import throughput. Fixes: `_canon_str` preserved money scale (was stripping trailing zeros); rollback test re-pointed at `normalize_row_full`.
- **Phase 2 (Data Operator ingestion hardening): COMPLETE (2026-08-27)** — ingestion already delivered in Slice 1; this loop added the Phase-2 test-loop coverage and UI polish rather than rebuilding. Added tests (now **47 total**): empty-file reject, consumer-cannot-upload (full RBAC matrix), file-hash reproducibility, **atomic rollback-on-failure** (injected mid-import error → nothing persists), raw immutability across re-upload, duplicate full-rows preserved, **1000-row large fixture**. Added UI import-details drill-down + error states. New docs: `entity-lifecycle.md`, `api.md`. **Scope divergence (honest):** Phase 2 said "do NOT normalize" but Slice 1 already implemented+tested normalization (downstream slices need it); kept it rather than remove working code.
- **Major Build Loop: COMPLETE (2026-08-27)** — Slices 2–5 implemented and verified end-to-end on Postgres/Docker. **112 backend tests, ruff clean, migrations 0001→0007.**
  - **Slice 2 (Validation+Exceptions):** config-driven rule engine (`app/validation/`, 15 rules as pure functions), `validation_runs`/`validation_results`/`exceptions` (unique `(loan_pk,rule_id)` upsert + auto-resolve on re-run, ADR-014), `POST /validate`, `GET /exceptions`(filter/search), `GET /summary`. 14/15 classes fire on the full tape (source_conflict needs servicer ingestion — deferred; rule+unit-test exist). Golden fixtures + injected-count tests green.
  - **Slice 3 (Reviewer workbench):** `review_decisions`, exception state machine (open→in_review→ignored/resolved), field edit → re-validation, loan approve/reject/request_correction (approve gated on zero open exceptions), optimistic concurrency `version`→**409**, `/exceptions/{id}/review`, `/loans/{pk}/fields|decision|comments|history`, RBAC. Reviewer UI (queue+filters+detail+decision).
  - **Slice 4 (AI copilot):** `ai_recommendations`+`ai_audit_logs`, deterministic exception-aware Mock (explain/suggest/note), evidence builder, Pydantic schema validation, **degraded path** (FailingProvider/malformed→logged), accept/edit/reject applied via review (AI never mutates), `/ai/*`. AI panel in reviewer UI.
  - **Slice 5 (Verified+Consumer+Trace):** `verified_loans` immutable versioned snapshots + reproducible `record_hash` (atomic verify, ADR-005/007/016), V2-supersedes-V1, `/loans/{pk}/verify`, `/verified-loans[/:id]`, `/export?format=csv|json`, `/trace/{loan_pk}` (full raw→verified lineage), consumer UI + export + traceability viewer. All 10 PS audit events emitted.
- **Final Hardening Loop: COMPLETE (2026-08-27)** — closed the top gaps. **121 backend tests, ruff clean, migrations 0001→0008, verified on Postgres/Docker.**
  - **`source_conflict` now LIVE (15/15 classes):** `servicer_records` model + `ingest_servicer_csv` (`POST /uploads?kind=servicer_update`) + validation loads servicer map; AI `resolve_conflict` compares both sources. Full tape → 759 exceptions incl. 506 source_conflict.
  - **Real bug found & fixed:** exceptions were unique on `(loan_pk, rule_id)`, so a rule firing on 2 fields (source_conflict on balance+status) collided. Changed key to `(loan_pk, rule_id, field)` (model + migration 0004 + service upsert). Regression test added.
  - **Demo seed:** `app/demo_seed.py` + `make demo-seed`/`demo-reset` — idempotent ingest tape+servicer+validate; demo fixtures shipped in `backend/seed/`. Verified: seeds 1000 loans/15 classes, skips on re-run.
  - **E2E + failure injection:** `test_e2e_journey` (full judge path), `test_failure_injection` (double-verify blocked, re-validation idempotent, multi-field regression, V1-hash-immutable-after-V2).
  - **Frontend:** servicer-feed upload (operator), "compare sources" AI button (reviewer).
- **Dataset-Truth Loop: COMPLETE (2026-08-27)** — proved the deterministic pipeline against ground truth. Built `scripts/reconcile_ground_truth.py` (engine vs 252-row ledger, TP/FN per class) + `scripts/data_quality_report.py` (machine-derived stats → `docs/dataset-quality-metrics.md`) + `tests/test_ground_truth.py` regression guard. `docs/dataset-completeness.md` = 21-field matrix + 15-class coverage + reconciliation.
  - **Reconciliation found 2 real false negatives** (invalid_date_format), both fixed with evidence: removed month-only `%b-%Y` date format (`Jan-2021` now correctly fails); `invalid_date_format` now flags empty **required** date fields; added config-driven `missing_required_field` rule (PS Module B). Result: **252/252, zero false negatives**. No ground-truth row modified.
  - **interest_rate ambiguity RESOLVED for this dataset** (measured: 997/1000 values percent-form 3–18; only sub-1 is an injected anomaly). Guard retained.
  - **124 backend tests, ruff clean, verified on Postgres** (invalid_date_format 6→8; L00046/L00047 now flagged). loan_tape hash unchanged.
- **Next (optional):** Playwright browser e2e; AI batch-summary/severity-classify kinds; real Anthropic provider wiring (interface ready).
