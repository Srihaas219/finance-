"""End-to-end judge journey through the real API (no mocked backend):
Operator login -> upload -> validate -> Reviewer AI -> apply -> approve -> verify ->
Consumer verified -> trace -> audit. Protects the demo path against regressions."""
import io

import pytest

from tests.conftest import auth
from tests.test_ingestion import HEADER, _row


@pytest.fixture(autouse=True)
def _isolate():
    from app.core.db import SessionLocal
    from app.models.ai import AIAuditLog, AIRecommendation
    from app.models.audit_event import AuditEvent
    from app.models.loan import Loan
    from app.models.raw_record import RawRecord
    from app.models.review import ReviewDecision
    from app.models.servicer import ServicerRecord
    from app.models.source_file import SourceFile
    from app.models.validation import LoanException, ValidationResult, ValidationRun
    from app.models.verified import VerifiedLoan

    db = SessionLocal()
    for model in (VerifiedLoan, AIRecommendation, AIAuditLog, ReviewDecision, ValidationResult,
                  LoanException, ValidationRun, AuditEvent, ServicerRecord, Loan, RawRecord, SourceFile):
        db.query(model).delete()
    db.commit()
    db.close()
    yield


def test_full_judge_journey(client, login):
    # A tape with one fixable exception (balance > principal) + one clean loan.
    tape = ("\n".join([
        HEADER,
        _row(loan_id="J1", principal="1000.00", balance="5000.00"),  # balance_gt_principal
        _row(loan_id="J2"),  # clean
    ]) + "\n").encode()

    # 1-2. Operator login + upload
    op = login(client, "operator@loantrust.demo", "operator123")
    up = client.post("/uploads", headers=auth(op),
                     files={"file": ("tape.csv", io.BytesIO(tape), "text/csv")}).json()
    assert up["imported_count"] == 2

    # 3-5. Validate -> exceptions appear
    val = client.post(f"/validate?source_file_id={up['id']}", headers=auth(op)).json()
    assert val["loans_evaluated"] == 2
    summ = client.get("/summary", headers=auth(op)).json()
    assert summ["open_exceptions"] >= 1

    # 6-7. Reviewer opens queue
    rv = login(client, "reviewer@loantrust.demo", "reviewer123")
    q = client.get("/exceptions?type=balance_gt_principal", headers=auth(rv)).json()
    ex = q["items"][0]
    assert ex["loan_id"] == "J1"

    # 8-9. Evidence + AI explain + suggest
    explain = client.post("/ai/request", headers=auth(rv),
                          json={"exception_id": ex["id"], "kind": "explain"}).json()
    assert explain["degraded"] is False
    sug = client.post("/ai/request", headers=auth(rv),
                      json={"exception_id": ex["id"], "kind": "suggest_correction"}).json()
    assert sug["suggested_field"] == "current_balance"

    # 10. Human decision: accept AI (applies via review edit) -> exception resolves
    applied = client.post(f"/ai/recommendations/{sug['id']}/apply", headers=auth(rv),
                          json={"disposition": "accepted"}).json()
    assert applied["applied"] is True

    # 12-13. Approve + verify -> immutable hashed record
    client.post(f"/loans/{ex['loan_pk']}/decision", headers=auth(rv), json={"action": "approve"})
    v = client.post(f"/loans/{ex['loan_pk']}/verify", headers=auth(rv)).json()
    assert v["version"] == 1 and len(v["record_hash"]) == 64

    # 14-16. Consumer sees verified + trace + audit
    co = login(client, "consumer@loantrust.demo", "consumer123")
    vlist = client.get("/verified-loans", headers=auth(co)).json()
    assert any(i["loan_id"] == "J1" for i in vlist["items"])
    trace = client.get(f"/trace/{ex['loan_pk']}", headers=auth(co)).json()
    assert trace["source_file"]["file_hash"]
    assert trace["ai_recommendations"]  # AI was used
    assert trace["verified_versions"][0]["record_hash"] == v["record_hash"]
    audit = client.get("/audit/J1", headers=auth(co)).json()
    types = {e["event_type"] for e in audit}
    assert {"loan.imported", "verified.created"}.issubset(types)

    # export works
    exp = client.get("/export?format=json", headers=auth(co))
    assert exp.status_code == 200 and "J1" in exp.text
