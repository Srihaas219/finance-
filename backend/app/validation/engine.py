"""Turns Loan models into LoanViews and runs the rule set. Pure w.r.t. the DB."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .config import Ruleset
from .rules import LoanView, RuleFinding, evaluate_dataset, evaluate_row, rule_source_conflict

CANONICAL = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]


def loan_to_view(loan: Any) -> LoanView:
    v: LoanView = {"_pk": loan.id}
    for f in CANONICAL:
        val = getattr(loan, f)
        # Numeric columns come back as Decimal already; keep them typed for rules.
        v[f] = val
    # Ensure money fields are Decimal for comparisons.
    for f in ("original_principal", "current_balance", "interest_rate"):
        if v[f] is not None and not isinstance(v[f], Decimal):
            v[f] = Decimal(str(v[f]))
    v["_provenance"] = loan.field_provenance or []
    return v


def run_rules(
    views: list[LoanView],
    rs: Ruleset,
    servicer_by_loan_id: dict[str, dict] | None = None,
) -> dict[str, list[RuleFinding]]:
    """Return {loan_pk: [findings]} for the whole dataset."""
    findings: dict[str, list[RuleFinding]] = {}

    for v in views:
        row = evaluate_row(v, rs)
        if servicer_by_loan_id and v.get("loan_id") in servicer_by_loan_id:
            row.extend(rule_source_conflict(v, servicer_by_loan_id[v["loan_id"]], rs))
        if row:
            findings.setdefault(v["_pk"], []).extend(row)

    for pk, fs in evaluate_dataset(views, rs).items():
        findings.setdefault(pk, []).extend(fs)

    return findings
