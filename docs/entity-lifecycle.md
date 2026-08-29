# Entity Lifecycle — Ingestion Layer

> Entities implemented so far (Slice 1 + Phase 2 hardening). Ownership, keys, constraints,
> immutability. Later slices add validation/exception/verified entities.

## SourceFile (Layer 1 — evidence)
- **Owns:** one uploaded file, preserved byte-for-byte (`content: LargeBinary`) with `file_hash` (SHA-256).
- **Keys:** PK `id` (uuid). Indexed `file_hash`. `duplicate_of` (nullable) → points at the original SourceFile when identical bytes are re-uploaded (ADR-013).
- **Timestamps:** `uploaded_at`.
- **Counts:** `row_count`, `imported_count`, `failed_count` (denormalized summary).
- **Lifecycle:** `created (on upload)` → terminal. Never mutated after the import transaction commits.
- **Immutability:** content + hash are write-once. A re-upload creates a NEW row (`duplicate_of` set); the original is untouched (test: `test_raw_immutable_across_reupload`).

## RawRecord (Layer 1 — evidence)
- **Owns:** one original CSV row, exactly as received (`raw_payload: JSON`).
- **Keys:** PK `id`. FK `source_file_id` → `source_files.id` (indexed). Indexed `row_hash`.
- **Fields:** `row_number` (stable position), `row_hash` (SHA-256 of canonicalized cells), `import_status` (imported|failed), `failure_reason`.
- **Lifecycle:** `created (during import)` → terminal. Immutable.
- **Immutability:** never updated/deleted. Duplicate content does not create new RawRecords (evidence reused). Full-row duplicates within one file ARE preserved (same `row_hash`, two rows) because duplicates are data to detect, not errors (test: `test_duplicate_full_rows_within_file_are_preserved`).

## Loan (Layer 2 — operational, canonical)
- **Owns:** the normalized 21-field canonical loan.
- **Keys:** PK `id`. FK `source_file_id`, FK `raw_record_id` → provenance chain. Indexed `loan_id`, `borrower_id`, `payment_status`, `status`.
- **Fields:** typed canonical fields (nullable — dirty values normalize to NULL with a note), `normalization_notes: JSON`, `normalization_status` (clean|attention, indexed), `field_provenance: JSON` (per-field lineage: raw_value→transformation→canonical_value→status), `status` (lifecycle state, currently `imported`).
- **Field provenance (ADR-020):** for each of the 21 fields, one record `{field, source_column, raw_value, transformation, canonical_value, status}` where status ∈ `empty|ok|coerced|failed|review`. Failed/flagged transformations are surfaced, never hidden. Embedded rather than a separate table for import throughput.
- **Lifecycle:** `imported` → (later) `normalized/validated/...` per `system-state-machine.md`.
- **Mutability:** editable later only via audited reviewer decisions on allow-listed fields; identity anchors (`loan_id, borrower_id, original_principal, origination_date`) are forbidden edits (data-contract).

## AuditEvent (append-only)
- **Owns:** one recorded state change.
- **Keys:** PK `id`. FK `source_file_id` (nullable). Indexed `event_type`, `loan_id`.
- **Fields:** `event_type`, `actor_id/role` (or `system`), `entity_type/id`, `payload: JSON`, `occurred_at`.
- **Lifecycle:** insert-only; never updated or deleted. Written in the SAME transaction as the change it describes (ADR-016), so a failed import leaves no orphan events (test: `test_rollback_on_failure_is_atomic`).
- **Events so far:** `file.uploaded`, `loan.imported`.

## Transaction & failure semantics
An upload is one transaction: SourceFile + RawRecords + Loans + AuditEvents commit together or not at all. Insert order is dependency-safe (source_files → raw_records → loans → audit_events) — required by Postgres FK enforcement; SQLite now also enforces FKs (`PRAGMA foreign_keys=ON`) so tests catch ordering bugs. On any error nothing persists (atomic rollback).

## Operational & trusted-output entities (built in Major Build Loop)

- **ValidationRun** (L2): one rule-engine execution; `ruleset_version`, `status`, `loans_evaluated`, `totals` JSON. Reproducible.
- **ValidationResult** (L2): a single failing rule outcome within a run (structured: rule_id, severity, field, observed_value, message). Passing rules aren't stored; run totals hold pass counts.
- **LoanException** (L2, table `exceptions`): open data-quality issue, unique `(loan_pk, rule_id)`. Created only by the engine. `status` open→in_review→ignored/resolved. `version` = optimistic lock (409 on stale). Auto-resolved on re-validation when the rule no longer fires.
- **ReviewDecision** (L2): append-only human action log — comment/edit_field/start_review/ignore_exception/approve/reject/request_correction/apply_ai. Distinct from AI output.
- **AIAuditLog** (L2): every AI call (prompt/model/provider/latency/context_hash/degraded/error), success or failure.
- **AIRecommendation** (L2): advisory output, schema-validated, `applied`/`disposition`. **Never written to `loans`**; applying routes through ReviewDecision + `edit_field`.
- **VerifiedLoan** (L3, trusted output): IMMUTABLE versioned snapshot, unique `(loan_pk, version)`, reproducible `record_hash` (shared `core.hashing`), `supersedes_version`. Corrections create V+1; V1 stays queryable. Never updated/deleted.

Import/ImportRun folded into SourceFile; ImportError/FailedRow folded into `raw_records`; ReviewerComment/FieldCorrection folded into ReviewDecision (no needless tables). LoanFieldProvenance realized as embedded JSON (ADR-020).

**Full lineage:** VerifiedLoan → ReviewDecision → AIRecommendation → Exception → ValidationResult → rule → Loan → field_provenance → RawRecord → SourceFile, exposed by `GET /trace/{loan_pk}`.
