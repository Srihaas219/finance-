# Data Lifecycle & Data Architecture

> Immutability tiers and the raw→verified lineage chain.

## Three Layers

### Layer 1 — Evidence (IMMUTABLE)
Written once at ingestion, never updated.

- **source_files**: `id`, `filename`, `kind` (loan_tape | servicer_update | document_manifest), `byte_size`, `file_hash` (SHA-256), `uploaded_by`, `uploaded_at`, `storage_uri`.
- **raw_records**: `id`, `source_file_id`, `row_number`, `raw_payload` (JSONB — exact original cells), `row_hash` (SHA-256), `import_status` (imported | failed), `failure_reason?`.

Rationale: PS Module A ("Store raw uploaded data", "Preserve source-file lineage"). Traceability score depends on being able to point at the exact original bytes for any field.

### Layer 2 — Operational State (MUTABLE workflow)
The current working view; evolves as reviewers act.

- **loans** (canonical): normalized typed fields for the 21 PS fields + `id`, `source_file_id`, `raw_record_id`, `status` (state machine), `created_at`, `updated_at`. This is the *working* record, distinct from the verified snapshot.
- **validation_runs**: `id`, `source_file_id`, `ruleset_version`, `started_at`, `finished_at`, `summary` (counts by severity/type).
- **validation_results**: `id`, `validation_run_id`, `loan_id`, `rule_id`, `passed` (bool), `severity`, `details`.
- **exceptions**: `id`, `loan_id`, `rule_id`, `type`, `severity` (deterministic), `status` (open | in_review | resolved | ignored), `opened_at`, `resolved_at?`. **Created only by the validation engine.**
- **review_decisions**: `id`, `loan_id`, `reviewer_id`, `action` (approve | reject | request_correction | edit_field | comment | ignore_exception), `field?`, `old_value?`, `new_value?`, `comment?`, `created_at`.
- **ai_recommendations**: `id`, `loan_id`, `exception_id?`, `kind` (explain | suggest_correction | conflict_resolution | reviewer_note | severity | batch_summary | rule_gen), `output` (JSONB), `applied` (bool, default false), `ai_audit_log_id`, `created_at`. **Never written to `loans`.**

### Layer 3 — Trusted Output (IMMUTABLE / VERSIONED)
Created at verification; snapshots frozen forever.

- **verified_loans**: `id`, `loan_id`, `version` (int, 1..N), `snapshot` (JSONB — full canonical field set at verification time), `validation_summary`, `reviewer_id`, `ai_used` (bool), `ai_recommendation_ids` (array), `verified_at`, `record_hash` (SHA-256 of canonical snapshot), `supersedes_version?`. Unique `(loan_id, version)`.

Corrections after V1 → new row V2; V1 is never mutated or deleted (PS: immutable snapshots, versioned history).

## Lineage Chain (every important field is traceable)

```
source_files (bytes + file_hash)
   └─ raw_records (raw_payload + row_hash)
        └─ loans (normalization: raw string -> typed canonical value)
             └─ validation_results / exceptions (deterministic rule outcomes)
                  └─ ai_recommendations (optional, advisory)
                  └─ review_decisions (human edits / approve)
                       └─ verified_loans[vN] (snapshot + record_hash)
                            └─ audit_events (every step above emits one)
```

Given any verified field, the API can walk back: `verified_loans.snapshot.field` → the `review_decision` that set it (if edited) → the `loans` normalized value → the `raw_records.raw_payload` original cell → the `source_files` upload. `GET /audit/:loanId` exposes this chain.

## Normalization Contract (raw → canonical)

Normalization is **lossless-preserving**: it never edits `raw_records`; it produces a typed `loans` row and records what it did.

| Field | Raw examples | Canonical form | Notes |
|---|---|---|---|
| dates (origination, maturity, last_payment, last_updated) | `2021-03-01`, `03/01/2021`, `1-Mar-21` | ISO `date`/`datetime` (UTC) | Unparseable → null + validation error, not a crash. |
| money (original_principal, current_balance) | `$1,200.50`, `1200.5`, `(500)` | `Decimal` | Strip currency/commas; parens = negative (flagged). |
| interest_rate | `4.5`, `0.045`, `4.5%` | percent as decimal, documented convention | Ambiguity is itself a validation signal. |
| payment_status | `Current`, `current`, `CURR`, `30DPD` | enum | Map via synonym table; unmapped → exception. |
| borrower_state | `CA`, `California`, `Calif.` | 2-letter USPS | Invalid → `invalid_state_code` exception. |
| ids (loan_id, borrower_id) | strings | trimmed string | Missing loan_id → `missing_loan_id`. |

Normalization outcomes (coercions, nulls introduced) are stored so the reviewer/consumer can see "was `$1,200.50`, normalized to `1200.50`".

## Mapping to PS "Intentional Data Issues" (all 15)

Every issue class maps to a deterministic rule (see `test-strategy.md` for fixtures):
missing loan id · duplicate loan id · duplicate (borrower+amount+orig_date) · invalid date format · maturity<origination · negative principal · current>original · rate out of range · payment_status vs days_past_due mismatch · missing document_status · loan_tape vs servicer_update conflict · stale by last_updated_at · invalid state code · repeated borrower records · closed-but-positive-balance.
