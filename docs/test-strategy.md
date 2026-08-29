# Test Strategy

> Determinism first. AI always Mock in tests. Coverage weighted to what judges score: validation correctness, traceability/hashing, AI boundaries, and the 3-role demo flow.

## Test pyramid

| Layer | Tool | Scope | Runs in CI |
|---|---|---|---|
| Unit | pytest | rule engine, normalization, hashing, canonicalizer, RBAC helpers | always |
| Contract | pytest | `AIProvider` interface — Mock & (recorded) real conform to schema | always (mock), gated (real) |
| Integration | pytest + httpx + test DB | API endpoints, transactions, audit atomicity, state machine | always |
| E2E | Playwright | 14-step 3-role demo flow through real FE+BE+DB | nightly / pre-demo |

## Golden fixtures (the heart of validation testing)
For each of the 15 intentional issue classes, a minimal CSV fixture + expected exception (type, severity). Use organizer `expected_exception_sample.csv` as the master golden set once available.

| # | Issue | Test id |
|---|---|---|
| 1 | Missing loan id | test_rule_missing_loan_id |
| 2 | Duplicate loan id | test_rule_dup_loan_id |
| 3 | Dup (borrower+amount+orig_date) | test_rule_dup_combo |
| 4 | Invalid date format | test_rule_bad_date |
| 5 | Maturity < origination | test_rule_maturity_before_orig |
| 6 | Negative principal | test_rule_negative_principal |
| 7 | Balance > original | test_rule_balance_gt_principal |
| 8 | Rate out of range | test_rule_rate_range |
| 9 | Pay status vs DPD mismatch | test_rule_status_dpd |
| 10 | Missing document status | test_rule_missing_docstatus |
| 11 | loan_tape vs servicer conflict | test_rule_source_conflict |
| 12 | Stale by last_updated_at | test_rule_stale |
| 13 | Invalid state code | test_rule_invalid_state |
| 14 | Repeated borrower records | test_rule_repeated_borrower |
| 15 | Closed but positive balance | test_rule_closed_positive |

## Critical invariant tests (must stay green)
- `test_ai_no_mutation` — after any AI call, `loans` unchanged; only `ai_recommendations`/`ai_audit_logs` written.
- `test_ai_output_schema` — malformed AI JSON is rejected and logged, never persisted as a field change.
- `test_record_hash_reproducible` — recompute hash from snapshot equals stored `record_hash`.
- `test_verify_atomic` — forced error mid-verify rolls back snapshot + audit together.
- `test_verified_immutable` — UPDATE/DELETE on `verified_loans` is blocked; correction creates v+1.
- `test_rbac_matrix` — each role gets 200 on allowed routes, 403 on forbidden.
- `test_raw_preserved` — `raw_records.raw_payload` byte-equal to original after normalization.
- `test_audit_completeness` — each of the 10 PS events is emitted by its trigger.
- `test_state_machine_forbidden` — forbidden transitions raise.

## AI testing approach
- Default `AI_PROVIDER=mock`; Mock returns deterministic fixtures keyed by (kind, exception_type) → assertable.
- Contract test asserts every provider returns schema-valid output for each of the 7 AI kinds.
- Degradation test: provider raises/timeouts → endpoint returns structured "unavailable", workflow proceeds.

## E2E (Playwright) — mirrors demo-readiness 14 steps
Operator upload → summary → open failing record → Reviewer AI explain → accept/edit/reject → approve → verify → Consumer verified dashboard → audit trail → API response.

## Coverage gates (CI fails below)
- Rule engine + normalization + hashing modules: ≥90% line.
- AI boundary + verification atomicity tests: must exist and pass (presence-gated).
- Everything else: report-only initially.

## Ground-truth reconciliation (dataset-truth loop)
`scripts/reconcile_ground_truth.py` ingests the real tape+servicer into a throwaway DB, runs the engine, and reconciles against the 252-row ledger computing TP/FN per class. `tests/test_ground_truth.py` runs it and asserts **zero false negatives** (252/252 injected issues detected). `scripts/data_quality_report.py` emits machine-derived stats to `docs/dataset-quality-metrics.md` (reproducible; no hand-typed numbers). This loop's reconciliation caught 2 real false negatives (fixed) — see `dataset-completeness.md`.

## Implemented so far (Loop 2 / Slice 0) — 23 tests passing
- `test_health.py` — root, `/healthz`, `/readyz` (db check).
- `test_auth.py` — login success/bad-password/unknown-user, `/auth/me` with/without/invalid token.
- `test_rbac.py` — full 3×3 role×route matrix (own route 200, cross role 403) + no-auth 401.
- `test_hashing.py` — canonical JSON key-order independence, hash reproducibility, Decimal normalization, known SHA-256 vector.
Run from `backend/` with the venv: `python -m pytest` (uses throwaway SQLite; Mock AI). Frontend verified via `npm run build` (typecheck + Vite build).

## Non-goals (per PS §16)
No load/security/pentest suites, no OCR/blockchain tests. Production security explicitly out of scope.
