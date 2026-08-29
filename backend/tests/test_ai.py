"""AI copilot: advisory-only boundary, deterministic mock, degraded path, apply-via-review."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.ingestion.service import ingest_csv
from app.models.ai import AIAuditLog
from app.models.loan import Loan
from app.models.validation import LoanException
from app.validation.service import run_validation
from tests.conftest import auth
from tests.test_ingestion import HEADER, _row


def _seed_exception(loan_id, **over):
    content = ("\n".join([HEADER, _row(loan_id=loan_id, **over)]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename=f"{loan_id}.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    ex = db.scalar(select(LoanException).where(LoanException.loan_id == loan_id))
    out = (ex.loan_pk, ex.id) if ex else (None, None)
    db.close()
    return out


def test_ai_explain_is_deterministic_and_logged(client, login):
    _, exid = _seed_exception("AIEXP", state="ZZ")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/request", headers=auth(token),
                    json={"exception_id": exid, "kind": "explain"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "explain"
    assert "invalid_state_code" in body["output"]["explanation"]
    assert body["degraded"] is False
    # audit log exists with prompt/model
    log = client.get(f"/ai/logs/{body['ai_audit_log_id']}", headers=auth(token)).json()
    assert log["provider"] == "mock" and log["model"] and log["prompt"]


def test_ai_never_mutates_canonical(client, login):
    loan_pk, exid = _seed_exception("AINOMUT", state="ZZ")
    db = SessionLocal()
    before = db.get(Loan, loan_pk).borrower_state
    db.close()
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    client.post("/ai/request", headers=auth(token), json={"exception_id": exid, "kind": "suggest_correction"})
    db = SessionLocal()
    after = db.get(Loan, loan_pk).borrower_state
    db.close()
    assert before == after == "ZZ"  # AI request must not change the loan


def test_ai_suggest_then_accept_applies_via_review_and_resolves(client, login):
    # balance_gt_principal has a deterministic suggestion (cap balance at principal).
    loan_pk, exid = _seed_exception("AISUG", principal="1000.00", balance="5000.00")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    rec = client.post("/ai/request", headers=auth(token),
                      json={"exception_id": exid, "kind": "suggest_correction"}).json()
    assert rec["suggested_field"] == "current_balance"
    assert rec["suggested_value"] == "1000.00"
    # Accepting applies through the HUMAN review path (edit_field) + re-validates.
    applied = client.post(f"/ai/recommendations/{rec['id']}/apply", headers=auth(token),
                          json={"disposition": "accepted"})
    assert applied.status_code == 200
    assert applied.json()["applied"] is True
    db = SessionLocal()
    ex = db.get(LoanException, exid)
    loan = db.get(Loan, loan_pk)
    status, bal = ex.status, loan.current_balance
    db.close()
    assert status == "resolved"
    assert str(bal) == "1000.00"


def test_ai_reject_does_not_mutate(client, login):
    loan_pk, exid = _seed_exception("AIREJ", principal="1000.00", balance="5000.00")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    rec = client.post("/ai/request", headers=auth(token),
                      json={"exception_id": exid, "kind": "suggest_correction"}).json()
    res = client.post(f"/ai/recommendations/{rec['id']}/apply", headers=auth(token),
                      json={"disposition": "rejected", "comment": "not confident"})
    assert res.json()["applied"] is False
    db = SessionLocal()
    bal = str(db.get(Loan, loan_pk).current_balance)
    db.close()
    assert bal == "5000.00"  # unchanged


def test_ai_degraded_path_when_provider_fails(client, login, monkeypatch):
    from app.ai import service
    from app.ai.provider import FailingProvider

    _, exid = _seed_exception("AIDEGR", state="ZZ")
    monkeypatch.setattr(service, "get_ai_provider", lambda s: FailingProvider())
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/request", headers=auth(token), json={"exception_id": exid, "kind": "explain"})
    assert r.status_code == 201  # degrades gracefully, does not error
    body = r.json()
    assert body["degraded"] is True
    assert "unavailable" in body["output"]["message"].lower()
    # failure is logged
    db = SessionLocal()
    log = db.get(AIAuditLog, body["ai_audit_log_id"])
    err, degraded = log.error, log.degraded
    db.close()
    assert degraded is True and err


def test_ai_malformed_output_degrades(client, login, monkeypatch):
    from app.ai import service

    _, exid = _seed_exception("AIMAL", state="ZZ")

    class BadProvider:
        name = "bad"
        model = "bad"

        def generate(self, kind, context):
            from datetime import UTC, datetime

            from app.ai.provider import AIResult
            return AIResult(kind=kind, output={"totally": "wrong shape"}, model="bad",
                            provider="bad", prompt="x", created_at=datetime.now(UTC).isoformat(),
                            latency_ms=0)

    monkeypatch.setattr(service, "get_ai_provider", lambda s: BadProvider())
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/request", headers=auth(token), json={"exception_id": exid, "kind": "explain"})
    assert r.status_code == 201
    assert r.json()["degraded"] is True  # schema validation failed -> degraded


def test_ai_batch_summary_is_advisory_and_read_only(client, login):
    # create a couple of exceptions
    _seed_exception("BS1", state="ZZ")
    _seed_exception("BS2", principal="1000.00", balance="9000.00")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models.loan import Loan
    db = SessionLocal()
    loans_before = db.scalar(select(func.count()).select_from(Loan))
    db.close()

    r = client.post("/ai/summarize-queue", headers=auth(token))
    assert r.status_code == 201 or r.status_code == 200
    body = r.json()
    assert body["stats"]["total"] >= 2
    assert "priority" in body
    assert body["narrative"]
    # read-only: no loans changed
    db = SessionLocal()
    loans_after = db.scalar(select(func.count()).select_from(Loan))
    db.close()
    assert loans_after == loans_before


def test_ai_batch_summary_rbac(client, login):
    for who in [("operator@loantrust.demo", "operator123"), ("consumer@loantrust.demo", "consumer123")]:
        tok = login(client, *who)
        assert client.post("/ai/summarize-queue", headers=auth(tok)).status_code == 403


def test_ai_rbac_operator_and_consumer_blocked(client, login):
    _, exid = _seed_exception("AIRBAC", state="ZZ")
    for who in [("operator@loantrust.demo", "operator123"), ("consumer@loantrust.demo", "consumer123")]:
        tok = login(client, *who)
        r = client.post("/ai/request", headers=auth(tok), json={"exception_id": exid, "kind": "explain"})
        assert r.status_code == 403


def test_ai_classify_severity_is_advisory_only(client, login):
    loan_pk, exid = _seed_exception("AICLSEV", state="ZZ")
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/request", headers=auth(token),
                    json={"exception_id": exid, "kind": "classify_severity"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "classify_severity"
    assert body["output"]["advisory"] is True
    assert "deterministic_severity" in body["output"]
    assert "suggested_severity" in body["output"]
    # Invariant: classify_severity must NOT mutate canonical loan data
    from app.core.db import SessionLocal
    from app.models.loan import Loan
    db = SessionLocal()
    loan = db.get(Loan, loan_pk)
    state_after = loan.borrower_state
    db.close()
    assert state_after == "ZZ"  # unchanged — AI never mutates


def test_ai_nl_rule_generation_advisory_only(client, login):
    """POST /ai/nl-rule returns advisory rule skeletons and never mutates canonical data."""
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/nl-rule", headers=auth(token),
                    json={"natural_language": "flag loans where interest rate is above 30%"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["output"]["advisory"] is True
    assert len(body["output"]["generated_rules"]) >= 1
    assert body["output"]["generated_rules"][0]["field"] == "interest_rate"
    assert "ai_audit_log_id" in body
    assert body["degraded"] is False


def test_ai_nl_rule_generation_rbac(client, login):
    """Only reviewers can generate rule skeletons."""
    for who in [("operator@loantrust.demo", "operator123"), ("consumer@loantrust.demo", "consumer123")]:
        tok = login(client, *who)
        r = client.post("/ai/nl-rule", headers=auth(tok),
                        json={"natural_language": "flag balance > principal"})
        assert r.status_code == 403
