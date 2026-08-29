"""Reviewer workbench: exception actions, optimistic concurrency (409), field edit ->
re-validation -> exception resolved, loan approve gating, RBAC."""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.ingestion.service import ingest_csv
from app.models.validation import LoanException
from app.validation.service import run_validation
from tests.conftest import auth
from tests.test_ingestion import HEADER, _row


def _seed_loan_with_exception(loan_id="RV1", **row_over):
    """Ingest one loan that fails a rule; validate; return (loan_pk, exception)."""
    content = ("\n".join([HEADER, _row(loan_id=loan_id, **row_over)]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename=f"{loan_id}.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    ex = db.scalar(select(LoanException).where(LoanException.loan_id == loan_id))
    result = (ex.loan_pk, ex.id, ex.version, ex.rule_id) if ex else (None, None, None, None)
    db.close()
    return result


def test_reviewer_can_start_and_ignore_exception(client, login):
    # maturity before origination -> high exception
    _, exid, ver, rule = _seed_loan_with_exception("RVIGN", orig="2025-01-01", mat="2020-01-01")
    assert rule == "maturity_before_origination"
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post(f"/exceptions/{exid}/review", headers=auth(token),
                    json={"action": "start_review", "expected_version": ver})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_review"
    new_ver = r.json()["version"]
    r2 = client.post(f"/exceptions/{exid}/review", headers=auth(token),
                     json={"action": "ignore", "comment": "known issue", "expected_version": new_ver})
    assert r2.status_code == 200
    assert r2.json()["status"] == "ignored"


def test_optimistic_concurrency_conflict(client, login):
    _, exid, ver, _ = _seed_loan_with_exception("RVCONC", orig="2025-01-01", mat="2020-01-01")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    # First reviewer succeeds (version advances).
    ok = client.post(f"/exceptions/{exid}/review", headers=auth(token),
                     json={"action": "start_review", "expected_version": ver})
    assert ok.status_code == 200
    # Second reviewer submits the STALE version -> 409.
    stale = client.post(f"/exceptions/{exid}/review", headers=auth(token),
                        json={"action": "ignore", "expected_version": ver})
    assert stale.status_code == 409


def test_field_edit_revalidates_and_resolves_exception(client, login):
    # invalid state -> fix it -> re-validation resolves the exception
    loan_pk, exid, _, rule = _seed_loan_with_exception("RVEDIT", state="ZZ")
    assert rule == "invalid_state_code"
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.patch(f"/loans/{loan_pk}/fields", headers=auth(token),
                     json={"field": "borrower_state", "value": "CA", "comment": "fixed"})
    assert r.status_code == 200, r.text
    assert r.json()["new"] == "CA"
    db = SessionLocal()
    ex = db.get(LoanException, exid)
    status = ex.status
    db.close()
    assert status == "resolved"  # engine cleared it on re-validation


def test_cannot_edit_forbidden_field(client, login):
    loan_pk, _, _, _ = _seed_loan_with_exception("RVFORBID", state="ZZ")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.patch(f"/loans/{loan_pk}/fields", headers=auth(token),
                     json={"field": "loan_id", "value": "HACKED"})
    assert r.status_code == 400


def test_approve_blocked_until_exceptions_cleared_then_allowed(client, login):
    loan_pk, exid, ver, _ = _seed_loan_with_exception("RVAPP", state="ZZ")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    # Approve blocked while exception open.
    blocked = client.post(f"/loans/{loan_pk}/decision", headers=auth(token),
                          json={"action": "approve"})
    assert blocked.status_code == 400
    # Ignore the exception, then approve succeeds.
    client.post(f"/exceptions/{exid}/review", headers=auth(token),
                json={"action": "ignore", "expected_version": ver})
    ok = client.post(f"/loans/{loan_pk}/decision", headers=auth(token), json={"action": "approve"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"


def test_rbac_operator_cannot_review(client, login):
    _, exid, ver, _ = _seed_loan_with_exception("RVRBAC", state="ZZ")
    op = login(client, "operator@loantrust.demo", "operator123")
    r = client.post(f"/exceptions/{exid}/review", headers=auth(op),
                    json={"action": "start_review", "expected_version": ver})
    assert r.status_code == 403
    con = login(client, "consumer@loantrust.demo", "consumer123")
    r2 = client.patch(f"/loans/{'x'}/fields", headers=auth(con),
                      json={"field": "borrower_state", "value": "CA"})
    assert r2.status_code == 403


def test_comment_and_history(client, login):
    loan_pk, _, _, _ = _seed_loan_with_exception("RVHIST", state="ZZ")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    client.post(f"/loans/{loan_pk}/comments", headers=auth(token), json={"comment": "looking into this"})
    hist = client.get(f"/loans/{loan_pk}/history", headers=auth(token)).json()
    assert any(h["action"] == "comment" for h in hist)
