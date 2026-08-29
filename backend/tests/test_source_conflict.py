"""Servicer second-source ingestion -> source_conflict rule -> AI resolve_conflict.
Completes the 15th issue class + the flagship AI conflict-comparison feature."""
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.ingestion.service import ingest_csv, ingest_servicer_csv
from app.models.validation import LoanException
from app.validation.service import run_validation
from tests.conftest import auth
from tests.test_ingestion import HEADER, _row


@pytest.fixture(autouse=True)
def _isolate():
    """Wipe ingestion/validation rows so fixed fixture bytes aren't deduped against
    another test's upload."""
    from app.models.ai import AIAuditLog, AIRecommendation
    from app.models.audit_event import AuditEvent
    from app.models.loan import Loan
    from app.models.raw_record import RawRecord
    from app.models.review import ReviewDecision
    from app.models.servicer import ServicerRecord
    from app.models.source_file import SourceFile
    from app.models.validation import ValidationResult, ValidationRun
    from app.models.verified import VerifiedLoan

    db = SessionLocal()
    for model in (VerifiedLoan, AIRecommendation, AIAuditLog, ReviewDecision, ValidationResult,
                  LoanException, ValidationRun, AuditEvent, ServicerRecord, Loan, RawRecord, SourceFile):
        db.query(model).delete()
    db.commit()
    db.close()
    yield

SERVICER_HEADER = "loan_id,current_balance,payment_status,days_past_due,last_updated_at,servicer_name,source_system"


def _seed_conflict():
    """loan_tape says balance 800; servicer says 300 -> source_conflict."""
    tape = ("\n".join([HEADER, _row(loan_id="SC1", balance="800.00", status="Current")]) + "\n").encode()
    servicer = ("\n".join([
        SERVICER_HEADER,
        "SC1,300.00,30 Days Late,15,2026-07-20,Acme,servicer_feed",
    ]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename="sc_tape.csv", content=tape,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    ingest_servicer_csv(db, filename="sc_srv.csv", content=servicer,
                        uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    ex = db.scalar(select(LoanException).where(
        LoanException.loan_id == "SC1", LoanException.rule_id == "source_conflict"))
    out = (ex.loan_pk, ex.id) if ex else (None, None)
    db.close()
    return out


def test_source_conflict_detected_from_servicer_feed():
    loan_pk, exid = _seed_conflict()
    assert exid is not None, "source_conflict was not raised"


def test_servicer_upload_via_api(client, login):
    token = login(client, "operator@loantrust.demo", "operator123")
    import io
    content = ("\n".join([SERVICER_HEADER, "APILN,100.00,Current,0,2026-07-01,Acme,servicer_feed"]) + "\n").encode()
    r = client.post("/uploads?kind=servicer_update", headers=auth(token),
                    files={"file": ("servicer_update.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "servicer_update"
    assert r.json()["imported_count"] == 1


def test_ai_resolve_conflict_compares_both_sources(client, login):
    loan_pk, exid = _seed_conflict()
    token = login(client, "reviewer@loantrust.demo", "reviewer123")
    r = client.post("/ai/request", headers=auth(token),
                    json={"exception_id": exid, "kind": "resolve_conflict"})
    assert r.status_code == 201, r.text
    out = r.json()["output"]
    assert out["kind"] == "resolve_conflict"
    sources = {v["source"] for v in out["values"]}
    assert sources == {"loan_tape", "servicer_feed"}
    # servicer feed is fresher (2026-07-20) -> recommends its value
    assert out["recommended_value"] is not None


def test_full_tape_with_servicer_covers_all_15_classes():
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    tape = repo / "data" / "raw" / "loan_tape.csv"
    srv = repo / "data" / "raw" / "servicer_update.csv"
    if not (tape.exists() and srv.exists()):
        import pytest
        pytest.skip("dataset not generated")
    db = SessionLocal()
    sf = ingest_csv(db, filename="full_tape.csv", content=tape.read_bytes(),
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    ingest_servicer_csv(db, filename="full_srv.csv", content=srv.read_bytes(),
                        uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    from sqlalchemy import func
    types = set(db.scalars(select(func.distinct(LoanException.exception_type))).all())
    db.close()
    all_15 = {
        "missing_loan_id", "duplicate_loan_id", "duplicate_combo", "invalid_date_format",
        "maturity_before_origination", "negative_principal", "balance_gt_principal",
        "rate_out_of_range", "status_dpd_mismatch", "missing_document_status", "source_conflict",
        "stale_record", "invalid_state_code", "repeated_borrower", "closed_positive_balance",
    }
    missing = all_15 - types
    assert not missing, f"missing classes: {missing}"
