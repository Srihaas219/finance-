"""Pure unit tests for the deterministic rule engine (no DB)."""
from datetime import date
from decimal import Decimal

from app.validation.config import load_ruleset
from app.validation.engine import run_rules
from app.validation.rules import (
    RuleFinding,
    evaluate_row,
    rule_source_conflict,
)

RS = load_ruleset("seed/validation_rules.json")


def _view(pk="p1", **over):
    base = {
        "_pk": pk, "loan_id": "L1", "borrower_id": "B1",
        "origination_date": date(2020, 1, 1), "maturity_date": date(2030, 1, 1),
        "original_principal": Decimal("1000"), "current_balance": Decimal("500"),
        "interest_rate": Decimal("5.0"), "payment_status": "Current", "days_past_due": 0,
        "borrower_state": "CA", "document_status": "complete",
        "last_updated_at": date(2026, 7, 1), "_provenance": [],
    }
    base.update(over)
    return base


def _codes(findings):
    return {f.rule_id for f in findings}


def test_clean_loan_has_no_findings():
    assert evaluate_row(_view(), RS) == []


def test_missing_loan_id():
    assert "missing_loan_id" in _codes(evaluate_row(_view(loan_id=None), RS))


def test_missing_required_field_non_date():
    # original_principal is required; empty -> missing_required_field
    codes = _codes(evaluate_row(_view(original_principal=None), RS))
    assert "missing_required_field" in codes


def test_missing_required_date_flagged_as_invalid_date():
    # a required date that is absent (empty provenance) -> invalid_date_format
    v = _view(origination_date=None, _provenance=[
        {"field": "origination_date", "status": "empty", "raw_value": ""}
    ])
    assert "invalid_date_format" in _codes(evaluate_row(v, RS))


def test_negative_principal():
    assert "negative_principal" in _codes(evaluate_row(_view(original_principal=Decimal("-5")), RS))


def test_balance_gt_principal():
    v = _view(original_principal=Decimal("100"), current_balance=Decimal("200"))
    assert "balance_gt_principal" in _codes(evaluate_row(v, RS))


def test_maturity_before_origination():
    v = _view(origination_date=date(2025, 1, 1), maturity_date=date(2020, 1, 1))
    assert "maturity_before_origination" in _codes(evaluate_row(v, RS))


def test_rate_out_of_range_high_and_fraction():
    assert "rate_out_of_range" in _codes(evaluate_row(_view(interest_rate=Decimal("45")), RS))
    assert "rate_out_of_range" in _codes(evaluate_row(_view(interest_rate=Decimal("0.045")), RS))


def test_status_dpd_mismatch_both_directions():
    assert "status_dpd_mismatch" in _codes(evaluate_row(_view(payment_status="Current", days_past_due=90), RS))
    assert "status_dpd_mismatch" in _codes(
        evaluate_row(_view(payment_status="90+ Days Late", days_past_due=0), RS)
    )


def test_missing_document_status():
    assert "missing_document_status" in _codes(evaluate_row(_view(document_status=None), RS))


def test_stale_record():
    assert "stale_record" in _codes(evaluate_row(_view(last_updated_at=date(2023, 1, 1)), RS))


def test_invalid_state_code():
    assert "invalid_state_code" in _codes(evaluate_row(_view(borrower_state="ZZ"), RS))


def test_closed_positive_balance():
    v = _view(payment_status="Closed", current_balance=Decimal("100"))
    assert "closed_positive_balance" in _codes(evaluate_row(v, RS))


def test_invalid_date_format_from_provenance():
    v = _view(origination_date=None, _provenance=[
        {"field": "origination_date", "status": "failed", "raw_value": "13/45/2021"}
    ])
    findings = evaluate_row(v, RS)
    assert "invalid_date_format" in _codes(findings)


def test_duplicate_loan_id_dataset_rule():
    views = [_view("p1", loan_id="DUP"), _view("p2", loan_id="DUP"), _view("p3", loan_id="UNIQUE")]
    res = run_rules(views, RS)
    assert "duplicate_loan_id" in _codes(res.get("p1", []))
    assert "duplicate_loan_id" in _codes(res.get("p2", []))
    assert "duplicate_loan_id" not in _codes(res.get("p3", []))


def test_duplicate_combo_dataset_rule():
    common = dict(borrower_id="BX", original_principal=Decimal("999"), origination_date=date(2021, 5, 1))
    views = [_view("p1", loan_id="A", **common), _view("p2", loan_id="B", **common), _view("p3", loan_id="C")]
    res = run_rules(views, RS)
    assert "duplicate_combo" in _codes(res.get("p1", []))
    assert "duplicate_combo" in _codes(res.get("p2", []))


def test_repeated_borrower_threshold():
    views = [_view(f"p{i}", loan_id=f"L{i}", borrower_id="BREPEAT") for i in range(5)]
    views.append(_view("solo", loan_id="LX", borrower_id="BONCE"))
    res = run_rules(views, RS)
    assert "repeated_borrower" in _codes(res.get("p0", []))
    assert "repeated_borrower" not in _codes(res.get("solo", []))


def test_source_conflict_rule():
    v = _view(current_balance=Decimal("500"), payment_status="Current")
    servicer = {"current_balance": "300", "payment_status": "30 Days Late"}
    findings = rule_source_conflict(v, servicer, RS)
    assert "source_conflict" in _codes(findings)
    assert len(findings) == 2  # both fields conflict


def test_findings_are_structured_not_strings():
    f = evaluate_row(_view(original_principal=Decimal("-5")), RS)[0]
    assert isinstance(f, RuleFinding)
    assert f.severity and f.field and f.message


def test_determinism_repeatable():
    v = _view(original_principal=Decimal("-5"), interest_rate=Decimal("99"))
    assert [(f.rule_id, f.message) for f in evaluate_row(v, RS)] == \
           [(f.rule_id, f.message) for f in evaluate_row(v, RS)]
