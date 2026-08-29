# Field Mapping — Source → Canonical

> Every canonical value must be traceable to a source column. Where two sources provide the
> same logical field, the system **must not silently pick one** — it detects the conflict,
> keeps both, and routes to human review (AI may assist, never decide).

## Pipeline (per field)

```
SOURCE FILE  →  RAW COLUMN  →  NORMALIZATION  →  CANONICAL FIELD  →  VALIDATION RULES
```

## Primary source: `loan_tape.csv` (1:1 column names)

`loan_tape.csv` uses the exact canonical column names (PS §6), so mapping is direct:

| Raw column (loan_tape) | Normalization | Canonical field | Rules |
|---|---|---|---|
| loan_id | trim | loan_id | missing_loan_id, duplicate_loan_id |
| borrower_id | trim | borrower_id | duplicate_combo, repeated_borrower |
| origination_date | multi-format→ISO | origination_date | invalid_date_format, maturity_before_origination |
| maturity_date | multi-format→ISO | maturity_date | invalid_date_format, maturity_before_origination |
| original_principal | strip `$`,`,`; parens=neg → Decimal | original_principal | negative_principal, balance_gt_principal |
| current_balance | strip `$`,`,` → Decimal | current_balance | balance_gt_principal, closed_positive_balance |
| interest_rate | strip `%` → Decimal | interest_rate | rate_out_of_range |
| borrower_state | upper; name→USPS | borrower_state | invalid_state_code |
| payment_status | synonym map → enum | payment_status | status_dpd_mismatch, closed_positive_balance |
| days_past_due | int | days_past_due | status_dpd_mismatch |
| last_updated_at | multi-format→ISO | last_updated_at | stale_record |
| document_status | lower | document_status | missing_document_status |
| *(remaining §6 fields)* | trim / typed cast | *(same name)* | soft enum/range flags |

## Second source: `servicer_update.csv` (conflict source)

Columns: `loan_id, current_balance, payment_status, days_past_due, last_updated_at, servicer_name, source_system` (source_system=`servicer_feed`). Linked to `loan_tape` by **`loan_id`**. Overlapping logical fields: `current_balance`, `payment_status`, `days_past_due`, `last_updated_at`, `servicer_name`.

### Conflict policy for overlapping fields
| Aspect | Decision |
|---|---|
| **Source priority** | Neither wins automatically. `loan_tape` is the *origination* record; `servicer_feed` is the *latest operational* record. Freshness (`last_updated_at`) is a **hint**, not an auto-resolver. |
| **Conflict detection** | For each overlapping field, compare normalized values per `loan_id`; a difference beyond tolerance (money: exact after rounding; enums: exact) → `source_conflict` exception (medium). |
| **Conflict resolution** | **Human review required.** Reviewer sees both values + timestamps + source, picks/edits one → recorded as a `review_decision` (audited). |
| **AI assistance** | **Eligible** — AI may *recommend* the more reliable value with reasoning (PS Module D “compare conflicting records”), but the recommendation is advisory and stored separately; a human applies it. |
| **Silent pick?** | **Forbidden.** No auto-merge, no last-write-wins on canonical data. |

## Third source: `document_manifest.csv` (enrichment)

Columns: `loan_id, document_status, documents_available, note`. Linked by **`loan_id`**. Used to (a) fill/validate `document_status` and (b) support a document-availability check (manifest `missing` / `documents_available=0`). Not a conflict source for financial fields.

## Join keys & cardinality
- **Primary key / join key:** `loan_id` (across all three files).
- `loan_tape` : `servicer_update` = 1 : 0..1 (not every loan has a servicer update).
- `loan_tape` : `document_manifest` = 1 : 0..1.
- `borrower_id` is a secondary grouping key (duplicate/repeat detection), **not** a join key.
- Rows with **blank `loan_id`** cannot be joined → they surface as `missing_loan_id` and are handled by row_number lineage instead.

## Provenance (traceability chain)
Each canonical field records where it came from so `GET /audit/:loanId` can walk it back:
```
verified_loans.snapshot.<field>
  ← review_decision (if a human edited it)          [who/when/old→new]
  ← loans.<field>  (normalization output)           [transform applied]
  ← raw_records.raw_payload[<raw column>]           [original cell + row_hash]
  ← source_files (file_hash, filename, uploader)    [original bytes]
```
For conflict fields, provenance also names which **source_system** each candidate value came from.
