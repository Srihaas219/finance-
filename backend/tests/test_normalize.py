"""Unit tests for the pure normalization functions (no DB)."""
from datetime import date
from decimal import Decimal

from app.ingestion.normalize import normalize_row


def _raw(**over):
    base = {f: "" for f in [
        "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
        "original_principal", "current_balance", "interest_rate", "term_months",
        "borrower_state", "loan_purpose", "credit_grade", "employment_length",
        "income_band", "payment_status", "days_past_due", "servicer_name",
        "last_payment_date", "last_updated_at", "document_status", "source_system",
    ]}
    base.update(over)
    return base


def test_money_and_date_and_state():
    c, notes = normalize_row(_raw(
        loan_id="L1", original_principal="$1,200.50", origination_date="2021-03-01",
        borrower_state="California", payment_status="current",
    ))
    assert c["original_principal"] == Decimal("1200.50")
    assert c["origination_date"] == date(2021, 3, 1)
    assert c["borrower_state"] == "CA"
    assert c["payment_status"] == "Current"
    assert notes == []


def test_parentheses_negative_money():
    c, _ = normalize_row(_raw(original_principal="(500.00)"))
    assert c["original_principal"] == Decimal("-500.00")


def test_unparseable_date_yields_null_and_note():
    c, notes = normalize_row(_raw(origination_date="not-a-date"))
    assert c["origination_date"] is None
    assert any(n["field"] == "origination_date" for n in notes)


def test_rate_fraction_flagged():
    c, notes = normalize_row(_raw(interest_rate="0.045"))
    assert c["interest_rate"] == Decimal("0.045")
    assert any("fraction" in n["note"] for n in notes)


def test_empty_values_are_none_not_error():
    c, notes = normalize_row(_raw())
    assert c["loan_id"] is None
    assert c["current_balance"] is None
    assert notes == []  # blank != dirty
