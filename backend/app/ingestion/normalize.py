"""Pure, deterministic normalization: raw CSV cell -> typed canonical value.

Independently testable; no DB, no AI. Contract in docs/data-contract.md. Normalization is
lossless-preserving: it never edits the raw row, only produces a typed value + a note when
it coerces or fails. Unparseable values become None with a note (validation flags them later).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Canonical column order (PS §6).
CANONICAL_FIELDS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]

# Only full-date formats (must include a day). Month-only forms like "Jan-2021" are
# intentionally NOT accepted for loan dates — an incomplete date is a validation signal
# (R-13), so they fall through to `invalid_date_format` rather than silently becoming the 1st.
_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y", "%Y/%m/%d"]

_PAYMENT_STATUS_MAP = {
    "current": "Current", "curr": "Current", "ok": "Current", "performing": "Current",
    "30 days late": "30 Days Late", "30dpd": "30 Days Late", "30": "30 Days Late",
    "60 days late": "60 Days Late", "60dpd": "60 Days Late", "60": "60 Days Late",
    "90+ days late": "90+ Days Late", "90 days late": "90+ Days Late", "90dpd": "90+ Days Late",
    "90": "90+ Days Late", "delinquent": "90+ Days Late",
    "closed": "Closed", "paid off": "Closed", "paidoff": "Closed", "paid": "Closed",
}

# Only unambiguous full state names are mapped. Short/ambiguous tokens (e.g. "Cal", "us")
# are intentionally NOT expanded — normalization ambiguity is a validation signal (R-13),
# so they fall through to `invalid_state_code`.
_STATE_NAME_TO_CODE = {
    "california": "CA", "new york": "NY", "texas": "TX", "florida": "FL", "washington": "WA",
}

_ISSUE = "note"


def _note(field: str, message: str) -> dict:
    return {"field": field, _ISSUE: message}


def normalize_date(raw: str, field: str, notes: list) -> date | None:
    v = (raw or "").strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    notes.append(_note(field, f"unparseable date '{raw}' -> null"))
    return None


def normalize_money(raw: str, field: str, notes: list) -> Decimal | None:
    v = (raw or "").strip()
    if not v:
        return None
    neg = v.startswith("(") and v.endswith(")")
    v = v.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    try:
        d = Decimal(v)
    except InvalidOperation:
        notes.append(_note(field, f"unparseable amount '{raw}' -> null"))
        return None
    if neg:
        d = -d
    return d


def normalize_rate(raw: str, field: str, notes: list) -> Decimal | None:
    v = (raw or "").strip().replace("%", "")
    if not v:
        return None
    try:
        d = Decimal(v)
    except InvalidOperation:
        notes.append(_note(field, f"unparseable rate '{raw}' -> null"))
        return None
    # UNCONFIRMED units: flag possible decimal-form (e.g. 0.045) rather than auto-scale.
    if Decimal(0) < d < Decimal(1):
        notes.append(_note(field, f"rate {d} looks like a fraction; expected percent units — review"))
    return d


def normalize_int(raw: str, field: str, notes: list) -> int | None:
    v = (raw or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        notes.append(_note(field, f"unparseable integer '{raw}' -> null"))
        return None


def normalize_state(raw: str, field: str, notes: list) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    low = v.lower()
    if low in _STATE_NAME_TO_CODE:
        return _STATE_NAME_TO_CODE[low]
    return v.upper()


def normalize_payment_status(raw: str, field: str, notes: list) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    return _PAYMENT_STATUS_MAP.get(v.lower(), v)


def _clean_str(raw: str) -> str | None:
    v = (raw or "").strip()
    return v or None


# Human-readable transformation label per canonical field (for provenance).
FIELD_TRANSFORMATIONS = {
    "loan_id": "trim", "borrower_id": "trim", "loan_type": "trim", "loan_purpose": "trim",
    "income_band": "trim", "servicer_name": "trim", "source_system": "trim",
    "origination_date": "parse_date", "maturity_date": "parse_date",
    "last_payment_date": "parse_date", "last_updated_at": "parse_date",
    "original_principal": "parse_currency", "current_balance": "parse_currency",
    "interest_rate": "parse_percent",
    "term_months": "parse_int", "days_past_due": "parse_int", "employment_length": "parse_int",
    "borrower_state": "usps_state", "payment_status": "map_status_enum",
    "credit_grade": "uppercase", "document_status": "lowercase",
}


def _canon_str(v) -> str | None:
    # Display representation for provenance: preserve the parsed scale (money keeps 2 dp).
    # (Hash-equivalence normalization lives in core.hashing, not here.)
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def normalize_row_full(raw: dict) -> tuple[dict, list, list]:
    """Return (canonical, notes, field_provenance).

    `field_provenance` is one record per canonical field with the raw value, the
    transformation applied, the canonical result, and a status:
      empty   - raw was blank -> canonical null (not an error)
      ok      - value unchanged by normalization
      coerced - value transformed (currency/date/case/trim/enum mapping)
      failed  - raw non-empty but unparseable -> canonical null
      review  - value kept but flagged for human attention (e.g. ambiguous rate units)
    Failed transformations are never hidden.
    """
    canonical, notes = normalize_row(raw)
    note_fields = {n["field"] for n in notes}

    provenance: list[dict] = []
    for field in CANONICAL_FIELDS:
        transformation = FIELD_TRANSFORMATIONS.get(field, "trim")
        raw_value = raw.get(field, "") or ""
        cval = canonical.get(field)
        cstr = _canon_str(cval)
        if raw_value.strip() == "":
            status = "empty"
        elif cval is None:
            status = "failed"
        elif cstr == raw_value:
            status = "ok"
        else:
            status = "coerced"
        # A note on a field whose value survived means "kept but flagged" -> review.
        if field in note_fields and cval is not None and status != "failed":
            status = "review"
        provenance.append(
            {
                "field": field,
                "source_column": field,
                "raw_value": raw_value,
                "transformation": transformation,
                "canonical_value": cstr,
                "status": status,
            }
        )
    return canonical, notes, provenance


def normalization_status(provenance: list[dict]) -> str:
    """clean unless any field failed or needs review."""
    return "attention" if any(p["status"] in ("failed", "review") for p in provenance) else "clean"


def normalize_row(raw: dict) -> tuple[dict, list]:
    """Return (canonical_dict, notes). Never raises on dirty values."""
    notes: list = []
    c: dict = {}
    c["loan_id"] = _clean_str(raw.get("loan_id"))
    c["borrower_id"] = _clean_str(raw.get("borrower_id"))
    c["loan_type"] = _clean_str(raw.get("loan_type"))
    c["origination_date"] = normalize_date(raw.get("origination_date"), "origination_date", notes)
    c["maturity_date"] = normalize_date(raw.get("maturity_date"), "maturity_date", notes)
    c["original_principal"] = normalize_money(raw.get("original_principal"), "original_principal", notes)
    c["current_balance"] = normalize_money(raw.get("current_balance"), "current_balance", notes)
    c["interest_rate"] = normalize_rate(raw.get("interest_rate"), "interest_rate", notes)
    c["term_months"] = normalize_int(raw.get("term_months"), "term_months", notes)
    c["borrower_state"] = normalize_state(raw.get("borrower_state"), "borrower_state", notes)
    c["loan_purpose"] = _clean_str(raw.get("loan_purpose"))
    c["credit_grade"] = (_clean_str(raw.get("credit_grade")) or "").upper() or None
    c["employment_length"] = normalize_int(raw.get("employment_length"), "employment_length", notes)
    c["income_band"] = _clean_str(raw.get("income_band"))
    c["payment_status"] = normalize_payment_status(raw.get("payment_status"), "payment_status", notes)
    c["days_past_due"] = normalize_int(raw.get("days_past_due"), "days_past_due", notes)
    c["servicer_name"] = _clean_str(raw.get("servicer_name"))
    c["last_payment_date"] = normalize_date(raw.get("last_payment_date"), "last_payment_date", notes)
    c["last_updated_at"] = normalize_date(raw.get("last_updated_at"), "last_updated_at", notes)
    c["document_status"] = (_clean_str(raw.get("document_status")) or "").lower() or None
    c["source_system"] = _clean_str(raw.get("source_system"))
    return c, notes
