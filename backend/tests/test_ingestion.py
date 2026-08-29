"""Slice 1 ingestion tests: raw preservation, normalization, dedupe, audit, RBAC, provenance."""
import io

from tests.conftest import auth

HEADER = (
    "loan_id,borrower_id,loan_type,origination_date,maturity_date,original_principal,"
    "current_balance,interest_rate,term_months,borrower_state,loan_purpose,credit_grade,"
    "employment_length,income_band,payment_status,days_past_due,servicer_name,"
    "last_payment_date,last_updated_at,document_status,source_system"
)


def _row(loan_id="L1", borrower_id="B1", orig="2021-03-01", mat="2026-03-01",
         principal="1200.50", balance="800.00", rate="4.500", state="CA",
         status="Current", dpd="0", doc="complete"):
    return (
        f"{loan_id},{borrower_id},Auto,{orig},{mat},{principal},{balance},{rate},36,{state},"
        f"Purchase,A,5,60-100k,{status},{dpd},Acme,2026-07-01,2026-07-15,{doc},origination_core"
    )


def _csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def _upload(client, login, content: bytes, filename="tape.csv", role=("operator@loantrust.demo", "operator123")):
    token = login(client, *role)
    return client.post(
        "/uploads",
        headers=auth(token),
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )


def test_upload_imports_rows_and_returns_summary(client, login):
    r = _upload(client, login, _csv(_row("L1"), _row("L2")))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["row_count"] == 2
    assert body["imported_count"] == 2
    assert body["failed_count"] == 0
    assert body["duplicate"] is False
    assert len(body["file_hash"]) == 64


def test_reviewer_cannot_upload(client, login):
    r = _upload(client, login, _csv(_row()), role=("reviewer@loantrust.demo", "reviewer123"))
    assert r.status_code == 403


def test_upload_requires_auth(client):
    r = client.post("/uploads", files={"file": ("t.csv", io.BytesIO(_csv(_row())), "text/csv")})
    assert r.status_code == 401


def test_raw_payload_preserved_exactly(client, login):
    # A dirty value must be preserved verbatim in the raw record, even though canonical is null.
    dirty = _row("L9", orig="not-a-date")
    up = _upload(client, login, _csv(dirty)).json()
    token = login(client, "operator@loantrust.demo", "operator123")
    loans = client.get(f"/loans?source_file_id={up['id']}", headers=auth(token)).json()["items"]
    loan_pk = loans[0]["id"]
    detail = client.get(f"/loans/{loan_pk}", headers=auth(token)).json()
    assert detail["provenance"]["raw_payload"]["origination_date"] == "not-a-date"
    assert detail["origination_date"] is None  # canonical coerced to null
    assert any(n["field"] == "origination_date" for n in detail["normalization_notes"])


def test_normalization_types(client, login):
    # NOTE: no thousands-comma here — an unquoted comma is (correctly) a malformed row.
    # The comma case is covered in test_normalize.py via a direct dict.
    up = _upload(client, login, _csv(_row("L5", principal="$1200.50", rate="4.5", state="California"))).json()
    token = login(client, "operator@loantrust.demo", "operator123")
    loan_pk = client.get(f"/loans?source_file_id={up['id']}", headers=auth(token)).json()["items"][0]["id"]
    d = client.get(f"/loans/{loan_pk}", headers=auth(token)).json()
    assert d["original_principal"] == 1200.5
    assert d["borrower_state"] == "CA"
    assert d["origination_date"] == "2021-03-01"


def test_malformed_row_marked_failed(client, login):
    # Extra column beyond the header -> structural failure, still preserved, no loan.
    bad = _row("L7") + ",EXTRA_COLUMN_VALUE"
    r = _upload(client, login, _csv(_row("L6"), bad)).json()
    assert r["row_count"] == 2
    assert r["imported_count"] == 1
    assert r["failed_count"] == 1
    assert r["failed_samples"][0]["row_number"] == 2


def test_duplicate_upload_reuses_evidence(client, login):
    content = _csv(_row("DUPX1"), _row("DUPX2"))  # unique content so this upload is the canonical original
    first = _upload(client, login, content).json()
    second = _upload(client, login, content).json()
    assert second["duplicate"] is True
    assert second["original_upload_id"] == first["id"]
    # No new loans created for the duplicate.
    token = login(client, "operator@loantrust.demo", "operator123")
    dup_loans = client.get(f"/loans?source_file_id={second['id']}", headers=auth(token)).json()
    assert dup_loans["total"] == 0


def test_audit_events_emitted(client, login):
    _upload(client, login, _csv(_row("LAUDIT")))
    token = login(client, "operator@loantrust.demo", "operator123")
    events = client.get("/audit/LAUDIT", headers=auth(token)).json()
    types = {e["event_type"] for e in events}
    assert "loan.imported" in types


def test_bad_header_rejected(client, login):
    r = _upload(client, login, b"foo,bar\n1,2\n")
    assert r.status_code == 400


def test_search_loans_by_id(client, login):
    _upload(client, login, _csv(_row("SEARCHME", borrower_id="BORR99")))
    token = login(client, "operator@loantrust.demo", "operator123")
    res = client.get("/loans?q=SEARCHME", headers=auth(token)).json()
    assert any(i["loan_id"] == "SEARCHME" for i in res["items"])
    res2 = client.get("/loans?q=BORR99", headers=auth(token)).json()
    assert any(i["borrower_id"] == "BORR99" for i in res2["items"])
