# Risk Register

> Phase D self-review, viewed as: hackathon judge · backend architect · DevOps · QA · malicious/buggy AI integration · future scaling engineer.
> Severity = Impact × Likelihood. P0 = must mitigate before/with the relevant slice.

## Judge's lens (what loses points)

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-01 | Demo breaks live (AI/API/DB flaky) | Kills Demo (10) + Completeness (20) | Mock AI default; seed + `demo-reset`; healthchecks; rehearse the 14-step flow | P0 |
| R-02 | Traceability not visibly demonstrated | Loses Traceability (10) | Audit viewer that walks raw→verified; show `record_hash` recompute | P0 |
| R-03 | AI looks like a gimmick / auto-applies | Loses AI (15) | Side-by-side AI-vs-decision UI; accept/edit/reject; visible prompt/model/timestamp | P0 |
| R-04 | Weak Agentic Coding evidence | Loses Agentic (15) | Maintain `ai-development-log.md` live: prompts, rejected outputs, % estimate | P0 |
| R-05 | Not runnable from README | Loses Completeness | `docker compose up --build` one-liner + seeded creds; test on clean clone | P0 |

## Backend architect's lens

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-10 | AI path can write canonical data (silent mutation) | Violates core rule | Hard boundary: `ai` module has no write access to `loans`; test `test_ai_no_mutation`; code review layering | P0 |
| R-11 | Non-reproducible hashes | Traceability collapses | Single canonicalizer (ADR-007); `test_record_hash_reproducible` | P0 |
| R-12 | Snapshot+audit not atomic | Corrupt history | Wrap verify in one txn; test rollback | P0 |
| R-13 | Normalization ambiguity (rate %, date locale) silently wrong | Bad data trusted | Treat ambiguity as a validation signal; store coercions; document conventions | P1 |
| R-14 | Duplicate-detection perf (O(n²)) | Slow import | Hash/group keys in-memory; indexes; fine at 5k | P2 |
| R-15 | Allowed-edit set too loose (edit identity keys) | Breaks lineage | Config allow-list; forbid `loan_id/borrower_id` edits w/o override+audit | P1 |

## DevOps lens

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-20 | Migrations not run / drift | App won't boot | Alembic auto-run on startup or entrypoint; `readyz` checks schema | P0 |
| R-21 | Secrets committed | Security embarrassment | `.env` gitignored; `.env.example`; no keys in repo | P0 |
| R-22 | Demo state polluted across runs | Confusing demo | `docker compose down -v` + `make seed`/`demo-reset` deterministic | P1 |
| R-23 | Port/host CORS mismatch FE↔BE | FE can't call API | Compose networking + CORS config from env | P1 |

## QA lens

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-30 | Rules untested against the 15 issue classes | Silent validation gaps | Fixture per issue class; `expected_exception_sample.csv` as golden | P0 |
| R-31 | AI tests flaky (real provider) | Red CI | Mock provider in tests; contract test the interface | P0 |
| R-32 | No e2e of the 3-role demo flow | Regressions in the thing judges see | Playwright e2e mirroring the 14-step demo | P1 |
| R-33 | RBAC not enforced server-side (UI-only) | Security/logic hole | `require_role` on every route; negative tests | P1 |

## Malicious / buggy AI integration lens

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-40 | AI returns malformed/oversized JSON | Crash/injection | Validate AI output against Pydantic schema; reject+log on fail | P0 |
| R-41 | Prompt injection via loan data cells | AI misbehaves | Data goes in a fenced/structured context; never execute AI output; humans gate all changes | P1 |
| R-42 | AI hallucinated correction applied blindly | Bad verified data | Human accept step mandatory; `applied` flag; audit both recommendation and decision | P0 |
| R-43 | AI cost/latency spike | Slow/expensive | Timeout + fallback to degraded; on-demand only; cache per (loan, kind) | P2 |
| R-44 | PII to external provider | Privacy | Synthetic data only; provider abstraction lets you redact/keep local | P2 |

## Future scaling engineer's lens

| ID | Risk | Impact | Mitigation | Sev |
|---|---|---|---|---|
| R-50 | Sync import won't scale to 100k+ | Timeouts | Documented trigger to add arq+Redis worker (scaling-strategy) | P2 |
| R-51 | Module boundaries erode over time | Monolith → big ball of mud | import-linter contract in CI; service-only cross-module calls | P2 |
| R-52 | Snapshot storage growth | Disk | Negligible now; archival strategy documented for later | P3 |

## Top mitigations to bake into Slice 1
R-05, R-20, R-21 (runnable + migrations + secrets) and R-01 (Mock AI + seed) are foundational and belong in the very first slice even though they aren't "features."

## Status update — Major Build Loop (validation→verification chain)
- Chain implemented + tested (112 tests, Postgres/Docker verified). Key invariant risks now TEST-COVERED: **R-10 AI silent mutation** → `test_ai_never_mutates_canonical` + apply-via-review; **R-11 hash reproducibility** → `test_record_hash_reproducible`; **R-12 atomic verify** → single-txn snapshot+audit; **R-40/R-42 malformed/hallucinated AI** → schema-validate→degraded + human gate (`test_ai_malformed_output_degrades`, `test_ai_reject_does_not_mutate`); **R-18 reviewer overwrite** → optimistic 409 (`test_optimistic_concurrency_conflict`); **R-33 RBAC** → per-endpoint matrix tests.
- **~~R-19b `source_conflict` deferred~~ → RESOLVED (Final Hardening).** Servicer ingestion (`servicer_records`, `POST /uploads?kind=servicer_update`) + validation servicer-map + AI `resolve_conflict` shipped. **15/15 classes live** on Postgres (506 source_conflict on the full tape). Regression: fixed a latent unique-key bug (see R-17b).
- **R-17b Multi-field exception unique-key bug (found+fixed).** Exceptions keyed `(loan_pk, rule_id)` collided when a rule fired on 2 fields (source_conflict). Fixed to `(loan_pk, rule_id, field)`; `test_multifield_rule_creates_distinct_exceptions` guards it. Sev: was P1, resolved.
- **New R-42b AI suggestions can be wrong on compound issues** (observed: negative-principal loan → negative suggested balance). Mitigation: advisory-only + mandatory human accept; both logged. Working as designed. Sev: P3.

## Reliability scenario decisions — Loop 3 (design; enforced in later slices)
| Scenario | Decision (ADR) | Status |
|---|---|---|
| S1 large file (10k rows) | sync + stream-parse + batched inserts; async trigger documented | designed (ADR-012) |
| S2 duplicate upload | new logical upload `duplicate_of`, reuse raw evidence, warn | designed (ADR-013) |
| S3 validation retry | versioned runs; exceptions upsert on `(loan_id, rule_id)`; run guard | designed (ADR-014/016) |
| S4 AI failure | timeout + schema-validate + degraded log; state untouched; Mock default | designed (ADR-017), Mock exists |
| S5 two reviewers | optimistic `version` column → 409 on stale write | designed (ADR-015) |
| S6 DB failure | change+audit and snapshot+audit each in one txn | designed (ADR-016) |

New tracked risks from this analysis:
- **R-16 Long sync import HTTP timeout at scale** — the 10× bottleneck. Impact: import fails on very large files. Mitigation: documented async trigger (>2s p95 / >100k rows); sync fine for competition scale. Sev: P2.
- **R-17 Concurrent validation runs racing** — Mitigation: run-status guard + exception upsert (ADR-014). Sev: P2.
- **R-18 Silent overwrite between reviewers** — Mitigation: optimistic locking (ADR-015). Sev: P1 (activate in review slice).

## Status update — Loop 2 (Slice 0)
- **R-05 (not runnable)** → MITIGATED: `docker compose up --build` verified to bring up db+api+web; README one-liner works.
- **R-20 (migrations/drift)** → MITIGATED: Alembic `0001_initial` runs on entrypoint; `/readyz` gates on DB; verified on fresh Postgres + SQLite.
- **R-21 (secrets committed)** → MITIGATED: `.gitignore` excludes `.env`/`.venv`/`node_modules`/`dist`/`*.db`; only `.env.example` committed; confirmed nothing sensitive staged.
- **R-33 (RBAC UI-only)** → PARTIALLY MITIGATED: server-side `require_role` enforced + tested (403 cross-role, 401 no token). Full matrix grows with each slice's routes.
- **Still open / next:** R-30 (rule fixtures), R-13 (normalization ambiguity) become active in Slices 1–2.

## Status update — Phase 2 (operator ingestion hardening)
- **R-12 (non-atomic writes)** → now TEST-COVERED for ingestion: `test_rollback_on_failure_is_atomic` injects a mid-import error and asserts zero persisted rows.
- **Raw immutability** → TEST-COVERED: `test_raw_immutable_across_reupload` (original raw byte-identical after a duplicate re-upload; duplicate creates no new evidence).
- **R-11 (hash reproducibility)** → ingestion file hash covered: `test_file_hash_reproducible`.
- **RBAC** → upload matrix complete: reviewer AND consumer rejected server-side (403), unauth 401.
- **Scale sanity** → `test_large_fixture_1000_rows` ingests the real 1000-row tape (1000/0). Confirms R-16 headroom at competition scale.

## Status update — Phase 1 (dataset intelligence)
- **New risk R-19 Synthetic ≠ real distributions.** Impact: rules tuned to synthetic data may mis-fire on the real organizer file. Mitigation: field contract is source-agnostic; thresholds externalized in `validation_rules.json`; swap real data via `download_datasets.py --organizer-dir` + re-profile; UNCONFIRMED items tracked in data-contract. Sev: P2.
- **R-13 (normalization ambiguity)** — `interest_rate` **RESOLVED for the supplied dataset** (measured: percent units; only sub-1 value is an injected anomaly). Guard retained for unknown real data. Separately, the reconciliation loop found+fixed the `%b-%Y` over-permissive date parse (another normalization-ambiguity instance): incomplete month-only dates now correctly fail. See `dataset-completeness.md`.
- **R-30 (rule fixtures)** MITIGATED: 15 golden fixtures + a 252-row ground-truth ledger (`expected_exception_sample.csv`) now exist to test validation against.
- **New R-20b Evidence tampering** — mitigated by `verify_datasets.py` (SHA-256 vs `data/manifest.json`) refusing silent replacement.

## Status update — Loop 3 (reliability/devops)
- Implemented NOW (verified): request-id + structured access logging (traceability seam), `/health` + `/ready` aliases, CI hardened with ruff lint + clean-DB migration check. 25 backend tests green, ruff clean.
- Everything else in this loop is documented design (ADR-012…018), intentionally NOT built — no queue/worker/k8s introduced (no measured trigger).
