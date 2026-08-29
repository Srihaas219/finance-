# Requirements Traceability Matrix

> Maps every Intain PS requirement → component → API → DB entity → UI screen → test → demo step → status.
> **Status legend:** ⬜ Not started · 🟡 Designed · 🟩 Implemented+tested.
> Nothing is marked 🟩 without evidence (passing test + working screen/API demo).

## Implementation status after Major Build Loop (2026-08-27) — evidence-backed

| PS Module | Status | Evidence |
|---|---|---|
| A. Ingestion | 🟩 | `test_ingestion*` (upload, raw preservation, dedupe, normalize, failed rows) + servicer feed; operator UI; Postgres 1000-row upload |
| B. Validation engine | 🟩 **(15/15 classes)** | `test_validation_rules` (18), `test_validation_integration`, `test_source_conflict` (servicer feed → source_conflict live); golden fixtures + full-tape all-15 coverage on Postgres |
| C. Exception queue | 🟩 | `GET /exceptions` filter/search; `test_review`; reviewer queue UI |
| C. Review actions | 🟩 | approve/reject/correct/comment/edit + optimistic 409 (`test_review`); reviewer UI |
| D. AI assistant | 🟩 | explain/suggest/note/classify_severity + **resolve_conflict (compares sources)** + **nl_rule_generation** + apply/reject + degraded (`test_ai`, `test_source_conflict`); AI panel UI; advisory-only enforced; 6 AI kinds total |
| E. Verified record | 🟩 | immutable snapshot + reproducible hash + V2 (`test_verification`, `test_failure_injection`); consumer UI |
| F. Audit trail | 🟩 | all 10 event types emitted (verified in live smoke); `/audit/:loanId` |
| G. Dashboards | 🟩 | 3 role dashboards (operator/reviewer/consumer), role-gated |
| H. Verified records API | 🟩 **(8/8)** | `/loans[/:id]`,`/exceptions[/:id]`,`/verified-loans[/:id][/versions]`,`/audit/:id`,`/summary`,`/export`,`/trace/:pk`,`/validate` |

**Full judge journey covered by `test_e2e_journey` (login→upload→validate→AI→apply→verify→consumer→trace→audit). Per-requirement rows below retain original design status; this table is the authoritative post-hardening state.**

## Module A — Data Ingestion

| Requirement | Component | API | DB Entity | UI Screen | Test | Demo step | Status |
|---|---|---|---|---|---|---|---|
| Upload CSV | ingestion | `POST /uploads` | source_files | Operator/Upload | test_upload_imports_rows | Upload messy tape | 🟩 |
| Parse records | ingestion | (in upload) | raw_records | Upload summary | test_upload_imports_rows | Import summary | 🟩 |
| Store raw uploaded data | ingestion | — | raw_records | — | test_raw_payload_preserved_exactly | — | 🟩 |
| Normalize to internal schema | ingestion | (in upload) | loans | Loan detail | test_normalize_* / test_normalization_types | — | 🟩 |
| Show upload summary | ingestion | `GET /uploads/:id` | source_files | Upload summary | test_upload_imports_rows | Import summary | 🟩 |
| Identify failed import rows | ingestion | `GET /uploads/:id` | raw_records.import_status | Upload summary | test_malformed_row_marked_failed | Import summary | 🟩 |
| Preserve source-file lineage | ingestion | `GET /loans/:id` (provenance) + `GET /audit/:loanId` | source_files/raw_records | Loan detail | test_raw_payload_preserved_exactly / test_audit_events_emitted | Inspect audit | 🟩 |

## Module B — Validation Engine

| Requirement | Component | API | DB Entity | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| Required fields present | validation | (in upload) | validation_results | Validation summary | test_rule_required | Validation summary | 🟡 |
| Valid dates/numeric | validation | — | validation_results | — | test_rule_dates/nums | — | 🟡 |
| No negative principal/balance | validation | — | validation_results | — | test_rule_negative | — | 🟡 |
| Maturity after origination | validation | — | validation_results | — | test_rule_matdate | — | 🟡 |
| Balance ≤ original principal | validation | — | validation_results | — | test_rule_balance | — | 🟡 |
| Valid payment status | validation | — | validation_results | — | test_rule_paystatus | — | 🟡 |
| Duplicate loan detection | validation | — | exceptions | — | test_rule_dupe | — | 🟡 |
| Required document status | validation | — | validation_results | — | test_rule_docstatus | — | 🟡 |
| Stale record detection | validation | — | exceptions | — | test_rule_stale | — | 🟡 |
| (conflict loan_tape vs servicer_update) | validation | — | exceptions | Loan detail | test_rule_conflict | AI conflict compare | 🟡 |

## Module C — Exception Queue

| Requirement | Component | API | DB | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| View exceptions | exceptions | `GET /exceptions` | exceptions | Reviewer/Queue | test_list_exceptions | Reviewer queue | 🟡 |
| Filter by type & severity | exceptions | `GET /exceptions?type=&severity=` | exceptions | Queue filters | test_filter_exceptions | — | 🟡 |
| Search by loan/borrower id | exceptions | `GET /exceptions?q=` | exceptions/loans | Queue search | test_search_exceptions | — | 🟡 |
| Open loan detail | review | `GET /loans/:id` | loans | Loan detail | test_loan_detail | Open failing record | 🟡 |
| Add review comments | review | `POST /loans/:id/comments` | review_decisions | Loan detail | test_add_comment | — | 🟡 |
| Approve/reject/request correction | review | `POST /loans/:id/decision` | review_decisions | Loan detail | test_decision_* | Approve/reject | 🟡 |
| Edit allowed fields | review | `PATCH /loans/:id/fields` | review_decisions/loans | Loan detail | test_edit_field / test_edit_forbidden | — | 🟡 |
| Track reviewer action history | review/audit | `GET /audit/:loanId` | audit_events | Audit viewer | test_action_history | — | 🟡 |

## Module D — AI Review Assistant

| Requirement | Component | API | DB | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| Explain failure | ai | `POST /ai/explain` | ai_recommendations/ai_audit_logs | AI panel | test_ai_explain_mock | AI explain exception | 🟡 |
| Suggest corrections | ai | `POST /ai/suggest` | ai_recommendations | AI panel | test_ai_suggest_mock | — | 🟡 |
| Compare conflicting records | ai | `POST /ai/resolve-conflict` | ai_recommendations | AI panel | test_ai_conflict_mock | Conflict compare | 🟡 |
| Generate reviewer notes | ai | `POST /ai/note` | ai_recommendations | AI panel | test_ai_note_mock | — | 🟡 |
| Classify severity | ai | `POST /ai/severity` | ai_recommendations | AI panel | test_ai_severity_mock | — | 🟡 |
| Summarize batch | ai | `POST /ai/summary` | ai_recommendations | Queue header | test_ai_batchsummary_mock | — | 🟡 |
| Generate rules/tests from NL | ai | `POST /ai/nl-rule` | ai_audit_logs | Reviewer NL panel | test_ai_nl_rule_generation_advisory_only / test_ai_nl_rule_generation_rbac | — | 🟩 |
| AI shown separate from decision | ai/review | (UI) | ai_recommendations vs review_decisions | AI panel | test_ai_not_applied | Accept/edit/reject AI | 🟡 |
| Accept/reject/edit AI | review | `POST /ai/:id/apply` | review_decisions | AI panel | test_ai_apply_human | Accept/edit/reject AI | 🟡 |
| Log AI in audit | ai/audit | — | ai_audit_logs/audit_events | Audit viewer | test_ai_logged | — | 🟡 |
| Show prompt/model/timestamp | ai | `GET /ai/logs/:id` | ai_audit_logs | AI panel/audit | test_ai_metadata | — | 🟡 |
| AI never silently mutates | ai/review | — | (invariant) | — | test_ai_no_mutation | — | 🟡 |

## Module E — Verified Loan Record

| Requirement | Component | API | DB | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| Canonical data + all metadata fields | verification | `POST /loans/:id/verify` | verified_loans | Loan detail | test_verify_snapshot | Create verified record | 🟡 |
| Source ref / validation / decision / AI used | verification | `GET /verified-loans/:id` | verified_loans | Consumer detail | test_verified_fields | — | 🟡 |
| Verification timestamp / verified-by | verification | — | verified_loans | — | test_verify_meta | — | 🟡 |
| Record hash | verification/core | — | verified_loans.record_hash | Consumer detail | test_record_hash_reproducible | — | 🟡 |

## Module F — Audit Trail (all 10 events)

| Event | Emitter | API | DB | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| File uploaded | ingestion | `GET /audit/:loanId` | audit_events | Audit viewer | test_audit_upload | — | 🟡 |
| Loan record imported | ingestion | — | audit_events | — | test_audit_import | — | 🟡 |
| Validation executed | validation | — | audit_events | — | test_audit_validate | — | 🟡 |
| Exception created | validation | — | audit_events | — | test_audit_exception | — | 🟡 |
| AI recommendation generated | ai | — | audit_events | Audit viewer | test_audit_ai | — | 🟡 |
| Reviewer comment added | review | — | audit_events | — | test_audit_comment | — | 🟡 |
| Field edited | review | — | audit_events | — | test_audit_edit | — | 🟡 |
| Loan approved/rejected | review | — | audit_events | — | test_audit_decision | — | 🟡 |
| Verified record created | verification | — | audit_events | Audit viewer | test_audit_verified | Inspect audit trail | 🟡 |
| Verified record exported | consumer | — | audit_events | — | test_audit_export | — | 🟡 |

## Module G — Dashboards

| Requirement | Component | API | DB | UI | Test | Demo | Status |
|---|---|---|---|---|---|---|---|
| Operator dashboard | operator FE | `GET /uploads`,`/uploads/:id`,`/operator/summary` | source_files/loans | Operator/Home + upload + history + details | test_ingestion*/test_ingestion_phase2* | Operator login → upload → summary | 🟩 |
| Reviewer dashboard | reviewer FE | `GET /exceptions`,`/summary` | * | Reviewer/Home | e2e_reviewer | Reviewer login | 🟡 |
| Consumer dashboard (quality score, history) | consumer FE | `GET /verified-loans`,`/summary` | * | Consumer/Home | e2e_consumer | Consumer login | 🟡 |

## Module H — Verified Records API (all 8 endpoints)

| Endpoint | Component | DB | Test | Demo | Status |
|---|---|---|---|---|---|
| `GET /loans` | review/consumer | loans | test_search_loans_by_id | — | 🟩 |
| `GET /loans/:id` | review | loans | test_raw_payload_preserved_exactly | Open record | 🟩 |
| `GET /exceptions` | exceptions | exceptions | test_api_exceptions | Reviewer queue | 🟡 |
| `GET /verified-loans` | consumer | verified_loans | test_api_verified | Consumer dashboard | 🟡 |
| `GET /verified-loans/:id` | consumer | verified_loans | test_api_verified_one | — | 🟡 |
| `GET /audit/:loanId` | audit | audit_events | test_api_audit | Inspect audit | 🟡 |
| `GET /summary` | * | * | test_api_summary | Validation summary | 🟡 |
| `GET /export` (verified CSV/JSON) | consumer | verified_loans | test_api_export | Show API/export | 🟡 |

## Deliverables (PS §12)

| Deliverable | Where | Status |
|---|---|---|
| GitHub repo, full source | repo root | ⬜ |
| Working app (hosted or local) | `docker compose up --build` | 🟡 (devops-plan) |
| README (setup, env, run) | `README.md` | ⬜ |
| Demo video ≤5 min | `demo-readiness.md` script | 🟡 |
| Architecture note 1–2 pages | `architecture.md` (condense) | 🟡 |
| AI Development Log | `ai-development-log.md` | 🟡 (live) |
| Test credentials (3 roles) | seed `users.json` + README | ⬜ |
| Sample output (verified dataset + audit export) | `/export` + seed | 🟡 |
