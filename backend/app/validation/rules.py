"""Deterministic validation rules — pure functions, no DB / HTTP / AI.

Each rule inspects a `LoanView` (typed canonical values + provenance) and yields
structured `RuleFinding`s. The set of findings for a dataset is fully determined by the
input + ruleset (reproducible). This module is the source of truth for exceptions; AI
never participates here.

Rule catalog (15) matches data/raw/validation_rules.json and the PS §7 issue classes.
`source_conflict` needs the second-source servicer file; it is defined as a cross-source
rule and applied by the service only when servicer data is present (see engine docstring).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from .config import Ruleset

LATE_STATUSES = {"30 Days Late", "60 Days Late", "90+ Days Late"}
DATE_FIELDS = ("origination_date", "maturity_date", "last_payment_date", "last_updated_at")


@dataclass
class RuleFinding:
    rule_id: str
    severity: str
    field: str | None
    observed_value: str | None
    message: str


# A LoanView is a plain dict built from a Loan model (see engine.loan_to_view).
LoanView = dict[str, Any]


def _prov_status(view: LoanView, field: str) -> str | None:
    for p in view.get("_provenance") or []:
        if p.get("field") == field:
            return p.get("status")
    return None


# ---------------------------------------------------------------- row-level rules

def rule_missing_loan_id(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    if not v.get("loan_id"):
        return [RuleFinding("missing_loan_id", rs.severity_of("missing_loan_id"),
                            "loan_id", None, "loan_id is missing")]
    return []


def rule_invalid_date_format(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    out = []
    for f in DATE_FIELDS:
        status = _prov_status(v, f)
        if status == "failed":
            raw = next((p["raw_value"] for p in v["_provenance"] if p["field"] == f), None)
            out.append(RuleFinding("invalid_date_format", rs.severity_of("invalid_date_format"),
                                   f, raw, f"{f} could not be parsed as a date"))
        elif status == "empty" and f in rs.required_fields:
            # A required date that is absent is a data-quality failure (PS: required fields present).
            out.append(RuleFinding("invalid_date_format", rs.severity_of("invalid_date_format"),
                                   f, None, f"required date {f} is missing"))
    return out


# Required fields already covered by a dedicated rule (skip to avoid duplicate exceptions).
_REQUIRED_COVERED_ELSEWHERE = {"loan_id", "origination_date", "maturity_date"}


def rule_missing_required_field(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    """PS Module B 'Required fields present' for fields not covered by a specific rule
    (loan_id -> missing_loan_id; required dates -> invalid_date_format)."""
    out = []
    for f in rs.required_fields:
        if f in _REQUIRED_COVERED_ELSEWHERE:
            continue
        val = v.get(f)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            out.append(RuleFinding("missing_required_field", rs.severity_of("missing_required_field"),
                                   f, None, f"required field {f} is missing"))
    return out


def rule_maturity_before_origination(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    o, m = v.get("origination_date"), v.get("maturity_date")
    if isinstance(o, date) and isinstance(m, date) and m < o:
        return [RuleFinding("maturity_before_origination", rs.severity_of("maturity_before_origination"),
                            "maturity_date", m.isoformat(), f"maturity {m} is before origination {o}")]
    return []


def rule_negative_principal(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    p = v.get("original_principal")
    if isinstance(p, Decimal) and p < 0:
        return [RuleFinding("negative_principal", rs.severity_of("negative_principal"),
                            "original_principal", str(p), "original_principal is negative")]
    return []


def rule_balance_gt_principal(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    p, b = v.get("original_principal"), v.get("current_balance")
    if isinstance(p, Decimal) and isinstance(b, Decimal) and b > p:
        return [RuleFinding("balance_gt_principal", rs.severity_of("balance_gt_principal"),
                            "current_balance", str(b), f"current_balance {b} exceeds original_principal {p}")]
    return []


def rule_rate_out_of_range(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    r = v.get("interest_rate")
    if isinstance(r, Decimal) and not (Decimal(str(rs.rate_min)) <= r <= Decimal(str(rs.rate_max))):
        msg = f"interest_rate {r} outside [{rs.rate_min},{rs.rate_max}]"
        return [RuleFinding("rate_out_of_range", rs.severity_of("rate_out_of_range"),
                            "interest_rate", str(r), msg)]
    return []


def rule_status_dpd_mismatch(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    status, dpd = v.get("payment_status"), v.get("days_past_due")
    if status is None or dpd is None:
        return []
    bad = (status == "Current" and dpd > 0) or (status in LATE_STATUSES and dpd == 0)
    if bad:
        msg = f"payment_status '{status}' inconsistent with days_past_due {dpd}"
        return [RuleFinding("status_dpd_mismatch", rs.severity_of("status_dpd_mismatch"),
                            "days_past_due", str(dpd), msg)]
    return []


def rule_missing_document_status(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    if not v.get("document_status"):
        return [RuleFinding("missing_document_status", rs.severity_of("missing_document_status"),
                            "document_status", None, "document_status is missing")]
    return []


def rule_stale_record(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    lu = v.get("last_updated_at")
    if isinstance(lu, date) and (rs.as_of_date - lu).days > rs.staleness_days:
        return [RuleFinding("stale_record", rs.severity_of("stale_record"),
                            "last_updated_at", lu.isoformat(),
                            f"last_updated_at {lu} older than {rs.staleness_days} days")]
    return []


def rule_invalid_state_code(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    st = v.get("borrower_state")
    if st and st not in rs.allowed_states:
        return [RuleFinding("invalid_state_code", rs.severity_of("invalid_state_code"),
                            "borrower_state", str(st), f"borrower_state '{st}' is not a valid USPS code")]
    return []


def rule_closed_positive_balance(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    status, b = v.get("payment_status"), v.get("current_balance")
    if status == "Closed" and isinstance(b, Decimal) and b > 0:
        return [RuleFinding("closed_positive_balance", rs.severity_of("closed_positive_balance"),
                            "current_balance", str(b), f"loan is Closed but current_balance {b} > 0")]
    return []


ROW_RULES = [
    rule_missing_loan_id,
    rule_missing_required_field,
    rule_invalid_date_format,
    rule_maturity_before_origination,
    rule_negative_principal,
    rule_balance_gt_principal,
    rule_rate_out_of_range,
    rule_status_dpd_mismatch,
    rule_missing_document_status,
    rule_stale_record,
    rule_invalid_state_code,
    rule_closed_positive_balance,
]


def evaluate_row(v: LoanView, rs: Ruleset) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for rule in ROW_RULES:
        findings.extend(rule(v, rs))
    return findings


# ---------------------------------------------------------------- dataset-level rules

def evaluate_dataset(views: list[LoanView], rs: Ruleset) -> dict[str, list[RuleFinding]]:
    """Cross-row rules. Returns {loan_pk: [findings]} keyed by the loan's internal id."""
    result: dict[str, list[RuleFinding]] = {}

    def add(pk: str, f: RuleFinding):
        result.setdefault(pk, []).append(f)

    # duplicate_loan_id
    by_loan_id: dict[str, list[LoanView]] = {}
    for v in views:
        lid = v.get("loan_id")
        if lid:
            by_loan_id.setdefault(lid, []).append(v)
    for lid, group in by_loan_id.items():
        if len(group) > 1:
            for v in group:
                add(v["_pk"], RuleFinding("duplicate_loan_id", rs.severity_of("duplicate_loan_id"),
                                          "loan_id", lid, f"loan_id '{lid}' appears {len(group)} times"))

    # duplicate_combo (borrower_id + original_principal + origination_date)
    by_combo: dict[tuple, list[LoanView]] = {}
    for v in views:
        b, p, o = v.get("borrower_id"), v.get("original_principal"), v.get("origination_date")
        if b and p is not None and o is not None:
            by_combo.setdefault((b, str(p), o.isoformat() if isinstance(o, date) else str(o)), []).append(v)
    for combo, group in by_combo.items():
        if len(group) > 1:
            for v in group:
                add(v["_pk"], RuleFinding("duplicate_combo", rs.severity_of("duplicate_combo"),
                                          "borrower_id", combo[0],
                                          f"borrower+principal+origination combo appears {len(group)} times"))

    # repeated_borrower (>= threshold occurrences)
    by_borrower: dict[str, list[LoanView]] = {}
    for v in views:
        b = v.get("borrower_id")
        if b:
            by_borrower.setdefault(b, []).append(v)
    for b, group in by_borrower.items():
        if len(group) >= rs.repeated_borrower_threshold:
            msg = f"borrower_id '{b}' appears {len(group)} times (>= {rs.repeated_borrower_threshold})"
            for v in group:
                add(v["_pk"], RuleFinding("repeated_borrower", rs.severity_of("repeated_borrower"),
                                          "borrower_id", b, msg))

    return result


def rule_source_conflict(v: LoanView, servicer_row: dict, rs: Ruleset) -> list[RuleFinding]:
    """Cross-source: compare canonical loan against a matched servicer_update row."""
    out = []
    for f in ("current_balance", "payment_status"):
        lv = v.get(f)
        sv = servicer_row.get(f)
        if sv in (None, ""):
            continue
        if str(lv) != str(sv):
            out.append(RuleFinding("source_conflict", rs.severity_of("source_conflict"),
                                   f, f"{lv} vs {sv}",
                                   f"{f} conflicts with servicer feed: loan_tape={lv}, servicer={sv}"))
    return out
