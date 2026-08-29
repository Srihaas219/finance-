# Loan Lifecycle State Machine

> One loan row moves through these states. Verified snapshots are separate immutable rows and are never mutated.

## States

Ingestion/validation phase (per loan, driven by system):
`IMPORTED → NORMALIZED → VALIDATED`
then VALIDATED forks by outcome:
- `CLEAN` — no exceptions.
- `EXCEPTION_OPEN` — one or more open exceptions.

Review phase (driven by Reviewer):
`EXCEPTION_OPEN → IN_REVIEW → { APPROVED | REJECTED | CORRECTION_REQUESTED }`
- `CORRECTION_REQUESTED → IN_REVIEW` (after edits) or back to operator.
- `CLEAN` or `APPROVED → VERIFIED_V1` (snapshot created).

Post-verification correction (new version, never overwrite):
`VERIFIED_Vn → NEEDS_REVERIFICATION → IN_REVIEW → APPROVED → VERIFIED_V(n+1)`

## Transition Table

| From | To | Role | Trigger | Audit event | Txn boundary |
|---|---|---|---|---|---|
| — | IMPORTED | system | raw row stored | `loan.imported` | per-import txn |
| IMPORTED | NORMALIZED | system | normalization | `loan.normalized`* | per-import txn |
| NORMALIZED | VALIDATED | system | validation run | `validation.executed` | per-run txn |
| VALIDATED | CLEAN | system | zero exceptions | `loan.clean`* | per-run txn |
| VALIDATED | EXCEPTION_OPEN | system | ≥1 exception | `exception.created` (×N) | per-run txn |
| EXCEPTION_OPEN | IN_REVIEW | Reviewer | opens loan / takes queue item | `review.started`* | request txn |
| IN_REVIEW | IN_REVIEW | Reviewer | comment / edit field / apply-or-reject AI | `comment.added` / `field.edited` / `ai.recommendation.decided` | request txn |
| IN_REVIEW | CORRECTION_REQUESTED | Reviewer | request correction | `loan.correction_requested` | request txn |
| CORRECTION_REQUESTED | IN_REVIEW | Reviewer/Operator | corrections submitted | `review.resumed`* | request txn |
| IN_REVIEW | REJECTED | Reviewer | reject | `loan.rejected` | request txn |
| IN_REVIEW / CLEAN | APPROVED | Reviewer | approve | `loan.approved` | request txn |
| APPROVED / CLEAN | VERIFIED_V1 | Reviewer (system snapshot) | create verified record | `verified.created` | verify txn (snapshot+hash+audit atomic) |
| VERIFIED_Vn | NEEDS_REVERIFICATION | system | new exception or correction after verify | `verified.reverification_needed`* | request txn |
| NEEDS_REVERIFICATION → … → VERIFIED_V(n+1) | (as above) | Reviewer | re-approval | `verified.created` (v=n+1, supersedes n) | verify txn |

\* Internal lifecycle events beyond the 10 PS-required audit events; kept for completeness but optional for MVP.

## Forbidden Transitions (must be rejected)

- Any write to a `verified_loans` row after creation (no UPDATE/DELETE). Corrections create a new version.
- `EXCEPTION_OPEN → VERIFIED_*` without passing through `APPROVED` (can't verify with open, non-ignored exceptions).
- AI causing any state transition on its own. AI never approves, verifies, or clears exceptions.
- `REJECTED → VERIFIED_*` directly.
- Editing a field outside the **allowed-edit set** (allowed set is config; e.g. dates, statuses, states — NOT `loan_id`/`borrower_id` identity keys without an explicit override + audit).
- Reducing version number, or two rows sharing `(loan_id, version)` (DB unique constraint).

## Invariants

1. `verified_loans` is append-only; `version` strictly increases per `loan_id`.
2. Exceptions are created/cleared only by the validation engine (deterministic), never by AI or by a bare human edit — a human edit triggers re-validation which may clear the exception.
3. Every transition that changes persisted state emits exactly one audit event within the same DB transaction.
4. A loan can be VERIFIED only if it has zero open, non-ignored, blocking-severity exceptions at snapshot time; the snapshot records which exceptions were ignored and why.
