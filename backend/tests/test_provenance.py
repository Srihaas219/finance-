"""Phase 3: per-field provenance + normalization status. Deterministic, no DB where possible."""
from app.ingestion.normalize import normalization_status, normalize_row_full

FIELDS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]


def _raw(**over):
    base = {f: "" for f in FIELDS}
    base.update(over)
    return base


def _prov(provenance, field):
    return next(p for p in provenance if p["field"] == field)


def test_provenance_covers_every_field():
    _, _, prov = normalize_row_full(_raw(loan_id="L1"))
    assert {p["field"] for p in prov} == set(FIELDS)
    for p in prov:
        assert set(p) == {"field", "source_column", "raw_value", "transformation", "canonical_value", "status"}


def test_currency_parsing_is_coerced_with_lineage():
    _, _, prov = normalize_row_full(_raw(original_principal="$1,200.50"))
    p = _prov(prov, "original_principal")
    assert p["raw_value"] == "$1,200.50"
    assert p["canonical_value"] == "1200.50"
    assert p["transformation"] == "parse_currency"
    assert p["status"] == "coerced"


def test_date_parsing_coerced_and_ok():
    _, _, prov = normalize_row_full(_raw(origination_date="03/01/2021", maturity_date="2026-03-01"))
    assert _prov(prov, "origination_date")["canonical_value"] == "2021-03-01"
    assert _prov(prov, "origination_date")["status"] == "coerced"
    assert _prov(prov, "maturity_date")["status"] == "ok"  # already ISO


def test_null_handling_is_empty_not_failed():
    _, _, prov = normalize_row_full(_raw(loan_id="L1"))  # everything else blank
    assert _prov(prov, "current_balance")["status"] == "empty"
    assert _prov(prov, "current_balance")["canonical_value"] is None


def test_invalid_value_is_failed_and_not_hidden():
    _, notes, prov = normalize_row_full(_raw(origination_date="not-a-date"))
    p = _prov(prov, "origination_date")
    assert p["status"] == "failed"
    assert p["canonical_value"] is None
    assert p["raw_value"] == "not-a-date"  # raw not hidden
    assert any(n["field"] == "origination_date" for n in notes)


def test_whitespace_trim_shows_as_coerced():
    _, _, prov = normalize_row_full(_raw(loan_id=" L1 "))
    p = _prov(prov, "loan_id")
    assert p["raw_value"] == " L1 "
    assert p["canonical_value"] == "L1"
    assert p["status"] == "coerced"


def test_case_normalization():
    _, _, prov = normalize_row_full(_raw(payment_status="current", borrower_state="california"))
    assert _prov(prov, "payment_status")["canonical_value"] == "Current"
    assert _prov(prov, "payment_status")["status"] == "coerced"
    assert _prov(prov, "borrower_state")["canonical_value"] == "CA"


def test_rate_fraction_is_review_status():
    _, _, prov = normalize_row_full(_raw(interest_rate="0.045"))
    p = _prov(prov, "interest_rate")
    assert p["status"] == "review"
    assert p["canonical_value"] == "0.045"  # value kept, flagged not dropped


def test_repeatability_same_input_same_provenance():
    a = normalize_row_full(_raw(loan_id="L1", original_principal="$1,200.50", origination_date="03/01/2021"))
    b = normalize_row_full(_raw(loan_id="L1", original_principal="$1,200.50", origination_date="03/01/2021"))
    assert a == b


def test_normalization_status_helper():
    _, _, clean = normalize_row_full(_raw(loan_id="L1", original_principal="$1,200.50"))  # coerced only
    assert normalization_status(clean) == "clean"
    _, _, bad = normalize_row_full(_raw(origination_date="not-a-date"))  # failed
    assert normalization_status(bad) == "attention"
