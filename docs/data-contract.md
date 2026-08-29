# Data Contract — Canonical Loan Model

> **Authority:** field names, types, and issue classes come from the Intain problem statement (`docs/reference/problem-statement-extracted.txt`, §6 fields, §7 issues, §5 files). Where the PS does not pin a value (e.g. exact rate convention), the choice is taken from the **synthetic bootstrap** `validation_rules.json` and marked accordingly. Mappings we cannot confirm against a real organizer file are marked **UNCONFIRMED**.
>
> **Dataset status:** organizer real files not shipped. Contract validated against the deterministic synthetic bootstrap in `data/raw/` (see `dataset-profile.md`). When the real package arrives, run `scripts/download_datasets.py --organizer-dir <path> --force` then re-profile; only the *example values* and *counts* should change, not the field contract.

## Canonical fields (21 — PS §6)

Legend — Req: required (R) / optional (O). Immutable = must never be silently changed (identity/evidence keys).

| # | Canonical field | Type | Req | Allowed range / values | Normalization | Key validation rules | Immutable? |
|---|---|---|---|---|---|---|---|
| 1 | `loan_id` | string | R | non-empty, unique | trim | `missing_loan_id`, `duplicate_loan_id` | **yes** |
| 2 | `borrower_id` | string | R | non-empty | trim | part of `duplicate_combo`, `repeated_borrower` | **yes** |
| 3 | `loan_type` | enum | O | Auto/Personal/Mortgage/Student/SMB | trim, title-case | unknown → low-sev flag | no |
| 4 | `origination_date` | date | R | ≤ `as_of`, ≤ maturity | multi-format → ISO date | `invalid_date_format`, `maturity_before_origination` | **yes** (anchors lineage) |
| 5 | `maturity_date` | date | R | > origination | multi-format → ISO date | `invalid_date_format`, `maturity_before_origination` | editable* |
| 6 | `original_principal` | decimal(2) | R | > 0 | strip `$`/commas, parens=neg → Decimal | `negative_principal`, `balance_gt_principal` | **yes** |
| 7 | `current_balance` | decimal(2) | R | 0 ≤ x ≤ original_principal (open) | strip `$`/commas → Decimal | `balance_gt_principal`, `closed_positive_balance` | editable* |
| 8 | `interest_rate` | decimal(3) | R | [rules.min, rules.max] = [0.5, 25.0] | strip `%` → Decimal (percent units) | `rate_out_of_range` | editable* |
| 9 | `term_months` | int | O | > 0 | int | consistency w/ dates (soft) | no |
| 10 | `borrower_state` | enum(USPS) | R | 50 states + DC | upper, map name→code | `invalid_state_code` | editable* |
| 11 | `loan_purpose` | enum | O | Purchase/Refi/… | trim | unknown → low flag | no |
| 12 | `credit_grade` | enum | O | A/B/C/D | upper | unknown → low flag | no |
| 13 | `employment_length` | int (years) | O | 0–60 | int | out-of-range → low flag | no |
| 14 | `income_band` | enum | O | <30k/30-60k/… | trim | unknown → low flag | no |
| 15 | `payment_status` | enum | R | rules.allowed_payment_status | map synonyms → enum | `status_dpd_mismatch`, `closed_positive_balance` | editable* |
| 16 | `days_past_due` | int | R | ≥ 0 | int | `status_dpd_mismatch` | editable* |
| 17 | `servicer_name` | string | O | free text | trim | — | no |
| 18 | `last_payment_date` | date | O | ≤ `as_of` | multi-format → ISO | `invalid_date_format` (soft) | editable* |
| 19 | `last_updated_at` | date/datetime | R | ≤ `as_of` | multi-format → ISO | `stale_record` (> staleness_days) | no |
| 20 | `document_status` | enum | R | complete/partial/missing | lower; cross-check manifest | `missing_document_status` | editable* |
| 21 | `source_system` | string | O | free text | trim | provenance only | no |

\* **editable** = in `validation_rules.json.allowed_edit_fields`; a reviewer may correct it (audited, re-validated). `forbidden_edit_fields = [loan_id, borrower_id, original_principal, origination_date]` — the identity/evidence anchors.

## Per-field notes (the tricky ones)

- **Dates (4,5,18,19):** raw arrives in many shapes (`2021-03-01`, `03/01/2021`, `1-Mar-21`, and deliberately broken like `13/45/2021`, `2021-13-01`, `not-a-date`). Normalization tries a fixed ordered list of formats; **unparseable → canonical `null` + `invalid_date_format` exception**, never a guess and never a crash. The raw string is preserved in `raw_records`.
- **Money (6,7):** strip `$` and thousands separators; `(500)` → `-500`. Store `Decimal` with 2 places. Negative principal and balance>principal are data signals, not parse errors.
- **interest_rate (8):** **UNCONFIRMED convention.** The synthetic data uses *percent units* (e.g. `4.5` = 4.5%). A real file might use decimal (`0.045`). Decision: treat values `0 < x < 1` as suspicious and flag for review rather than auto-scaling — ambiguity is a validation signal (R-13). Range check uses percent units from rules.
- **payment_status (15):** normalized via a synonym map (`current/curr/Current` → `Current`; `30DPD/30 days late` → `30 Days Late`; `paid off/closed` → `Closed`). Unmapped value → low-sev flag. The DPD-consistency rule (`status_dpd_mismatch`) runs on the normalized enum.
- **document_status (20):** present on the loan row *and* cross-checkable against `document_manifest.csv` by `loan_id`. Blank on the loan row → `missing_document_status`; manifest `missing` can raise a document-availability exception.
- **last_updated_at (19):** drives `stale_record` using `rules.staleness_days` (365) relative to `rules.as_of_date`. Fixed `as_of` keeps staleness deterministic.

## Provenance (implemented — Phase 3, ADR-020)
Every imported loan carries `field_provenance`: one record per field with `{raw_value, transformation, canonical_value, status}` where status ∈ `empty|ok|coerced|failed|review`. `normalization_status` = `attention` if any field failed/needs review. Exposed via `GET /loans/:id` and filterable via `GET /loans?attention=true`. Example: `origination_date '13/45/2021' → null [failed via parse_date]`.

## What is preserved vs transformable
- **Immutable evidence:** the raw uploaded bytes (`source_files`) and every original cell (`raw_records.raw_payload`). Never edited.
- **Transformable:** the canonical `loans` row (normalization output) and reviewer-editable fields (allow-list above), always audited and re-validated.
- **Never silently changed:** identity/evidence anchors (`loan_id, borrower_id, original_principal, origination_date`); any conflicting value between sources (must go to human review — see field-mapping.md); anything AI suggests (advisory only).

## Uncertainty register
| Item | Why unconfirmed | Resolution when real data arrives |
|---|---|---|
| `interest_rate` units (percent vs decimal) | **RESOLVED for this dataset** (see below); still unconfirmed for unknown real data | Inspect real distribution; keep the “0<x<1 suspicious” guard |

**interest_rate — resolved for the supplied dataset (2026-08-27):** measured 1000 rates → 997 legitimate values in 3.0–18.0 (**percent units**); the only sub-1 value (`0.1`) is an injected out-of-range anomaly, not a fractional rate. The system treats rates as percent and flags `0<x<1` as `review` (safety net). Deterministic; no guessing. Full analysis in `dataset-completeness.md §rate`.
| `last_updated_at` date vs datetime | PS field name suggests timestamp; synthetic emits date | Accept both in normalizer; store as datetime |
| `document_status` allowed set | PS lists the field, not its enum | Derive enum from real file; rules.json already externalizes it |
| exact required-field set | PS Module B says “required fields present” without listing | Currently from rules.required_fields; confirm against organizer rules |
