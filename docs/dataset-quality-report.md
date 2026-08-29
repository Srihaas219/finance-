# Dataset Quality Report — Intentional Issue Classes

> The 15 issue classes are defined by the problem statement (§7). Counts below are **ground truth** from the deterministic synthetic bootstrap (`data/raw/expected_exception_sample.csv`, seed 20260827, as_of 2026-08-01). Detection is **deterministic** — no AI is involved in creating or clearing an exception. The application's job is to *detect and manage* these, never to silently "fix" the data.

## Summary
- Total seeded exceptions: **252** across **15 classes**. By severity: **high 40 · medium 189 · low 23**.
- `source_conflict` (166) dominates by design — the servicer feed disagrees with the loan tape on ~half its rows, mirroring real operational reality; it's the flagship case for the AI "compare conflicting records" feature.
- These same fixtures become the validation golden set (`tests/fixtures/golden/*.csv` for single-file issues).

## Issue catalog

| Code | Description | File(s) | Field(s) | Detection logic | Severity | Count | Auto rule? | Human review? | AI useful? |
|---|---|---|---|---|---|---|---|---|---|
| `missing_loan_id` | loan_id blank | loan_tape | loan_id | value is empty/whitespace | high | 5 | ✅ | ✅ (source lookup) | explain only |
| `duplicate_loan_id` | loan_id repeats | loan_tape | loan_id | count(loan_id) > 1 | high | 5 | ✅ | ✅ | which is canonical |
| `duplicate_combo` | same borrower+principal+orig date | loan_tape | borrower_id, original_principal, origination_date | group key count > 1 | medium | 4 | ✅ | ✅ | likely-dupe reasoning |
| `invalid_date_format` | unparseable date | loan_tape | origination_date / maturity_date | not parseable by format list | high | 8 | ✅ | ✅ | suggest correction |
| `maturity_before_origination` | maturity < origination | loan_tape | maturity_date | maturity_date < origination_date | high | 6 | ✅ | ✅ | suggest plausible date |
| `negative_principal` | principal < 0 | loan_tape | original_principal | value < 0 | high | 5 | ✅ | ✅ | explain |
| `balance_gt_principal` | balance > principal | loan_tape | current_balance | current_balance > original_principal | high | 6 | ✅ | ✅ | explain / suggest |
| `rate_out_of_range` | rate outside [0.5,25] | loan_tape | interest_rate | rate < min or > max (rules.json) | medium | 6 | ✅ | ✅ | suggest / units check |
| `status_dpd_mismatch` | status vs DPD inconsistent | loan_tape | payment_status, days_past_due | Current & dpd>0, or 90+ & dpd=0 | medium | 7 | ✅ | ✅ | explain inconsistency |
| `missing_document_status` | document_status blank | loan_tape (+manifest) | document_status | value empty (cross-check manifest) | low | 8 | ✅ | optional | note |
| `source_conflict` | loan_tape vs servicer disagree | loan_tape + servicer_update | current_balance, payment_status | normalized values differ per loan_id | medium | 166 | ✅ | ✅ | **recommend reliable value** |
| `stale_record` | not updated in window | loan_tape | last_updated_at | as_of − last_updated_at > staleness_days | low | 10 | ✅ | optional | note |
| `invalid_state_code` | bad USPS state | loan_tape | borrower_state | not in allowed_states | medium | 6 | ✅ | ✅ | suggest correction |
| `repeated_borrower` | one borrower on many loans | loan_tape | borrower_id | count(borrower_id) ≥ threshold | low | 5 | ✅ | optional | pattern summary |
| `closed_positive_balance` | Closed but balance>0 | loan_tape | payment_status, current_balance | status=Closed & balance>0 | high | 5 | ✅ | ✅ | explain / suggest |

## Notes on detection
- **Cross-file rules** (`source_conflict`, and document-availability via manifest) require joining on `loan_id`; blank-`loan_id` rows are excluded and instead flagged `missing_loan_id`.
- **Thresholds are config** (`validation_rules.json`): rate range, staleness days, allowed states/statuses, required fields, repeated-borrower threshold. Changing the ruleset changes counts — runs are stamped with `ruleset_version` (ADR-011/014).
- **Severity is deterministic** (from rules), so AI severity-classification is a *secondary opinion*, never the source of truth.

## `source_conflict` — now live (Final Hardening)
The 15th class is fully wired: `servicer_update.csv` is ingested via `POST /uploads?kind=servicer_update` into `servicer_records` (normalized to match canonical loans), and validation loads a per-loan servicer map so the deterministic `source_conflict` rule compares `current_balance`/`payment_status`. On the full synthetic tape this yields ~506 conflicts (servicer feed disagrees on ~half its rows). AI `resolve_conflict` presents both sources and recommends the fresher value (advisory; a human applies). This is the flagship "compare conflicting records" feature. **All 15/15 issue classes are detected on Postgres.**

## Do-not-modify principle
Fixtures and raw files are **evidence**. We never hand-edit them to pass validation. If a rule needs tuning, we change `validation_rules.json` (versioned), not the data.
