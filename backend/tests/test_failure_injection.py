"""Failure injection / hardening: double-verify, re-validation idempotency (upsert),
multi-field exception regression, verified immutability."""
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.ingestion.service import ingest_csv, ingest_servicer_csv
from app.models.validation import LoanException
from app.validation.service import run_validation
from tests.conftest import auth
from tests.test_ingestion import HEADER, _row

SERVICER_HEADER = "loan_id,current_balance,payment_status,days_past_due,last_updated_at,servicer_name,source_system"


def test_loan_status_reflects_exceptions_after_validation():
    """Regression: loan.status must be 'exception' when it has open exceptions and 'clean'
    otherwise (broke when validation queried exceptions before flushing; autoflush=False)."""
    content = ("\n".join([HEADER,
                          _row(loan_id="STAT_BAD", borrower_id="BSB", state="ZZ"),  # invalid_state_code
                          # distinct borrower/principal so it doesn't share a duplicate_combo
                          _row(loan_id="STAT_OK", borrower_id="BSO", principal="4321.00")]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename="stat.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    from app.models.loan import Loan
    bad = db.scalar(select(Loan).where(Loan.loan_id == "STAT_BAD"))
    ok = db.scalar(select(Loan).where(Loan.loan_id == "STAT_OK"))
    bad_status, ok_status = bad.status, ok.status
    db.close()
    assert bad_status == "exception"
    assert ok_status == "clean"


def test_revalidation_is_idempotent_no_duplicate_exceptions():
    content = ("\n".join([HEADER, _row(loan_id="IDEMP", state="ZZ")]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename="idemp.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    run_validation(db, source_file_id=sf["id"])  # second run must upsert, not duplicate
    run_validation(db, source_file_id=sf["id"])
    n = db.scalar(select(func.count()).select_from(LoanException)
                  .where(LoanException.loan_id == "IDEMP", LoanException.rule_id == "invalid_state_code"))
    db.close()
    assert n == 1  # exactly one, despite three runs


def test_multifield_rule_creates_distinct_exceptions():
    """Regression: source_conflict fires on 2 fields -> 2 exceptions (was a unique-key bug)."""
    tape = ("\n".join([HEADER, _row(loan_id="MF1", balance="800.00", status="Current")]) + "\n").encode()
    srv = ("\n".join([SERVICER_HEADER, "MF1,300.00,30 Days Late,15,2026-07-20,Acme,servicer_feed"]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename="mf_tape.csv", content=tape,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    ingest_servicer_csv(db, filename="mf_srv.csv", content=srv,
                        uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    fields = set(db.scalars(select(LoanException.field).where(
        LoanException.loan_id == "MF1", LoanException.rule_id == "source_conflict")).all())
    db.close()
    assert fields == {"current_balance", "payment_status"}


def _clean_verified(client, login, loan_id="FI_VER"):
    content = ("\n".join([HEADER, _row(loan_id=loan_id)]) + "\n").encode()
    db = SessionLocal()
    sf = ingest_csv(db, filename=f"{loan_id}.csv", content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"])
    from app.models.loan import Loan
    pk = db.scalar(select(Loan.id).where(Loan.loan_id == loan_id))
    db.close()
    t = login(client, "reviewer@loantrust.demo", "reviewer123")
    client.post(f"/loans/{pk}/decision", headers=auth(t), json={"action": "approve"})
    v = client.post(f"/loans/{pk}/verify", headers=auth(t)).json()
    return pk, v, t


def test_double_verify_blocked(client, login):
    pk, v1, t = _clean_verified(client, login, "FI_DBL")
    # loan is now status=verified -> verifying again is rejected (400)
    again = client.post(f"/loans/{pk}/verify", headers=auth(t))
    assert again.status_code == 400


def test_verified_v1_hash_unchanged_after_v2(client, login):
    pk, v1, t = _clean_verified(client, login, "FI_IMMUT")
    # make a change and re-verify -> V2, V1 hash must be untouched
    client.patch(f"/loans/{pk}/fields", headers=auth(t), json={"field": "borrower_state", "value": "NY"})
    client.post(f"/loans/{pk}/decision", headers=auth(t), json={"action": "approve"})
    v2 = client.post(f"/loans/{pk}/verify", headers=auth(t)).json()
    db = SessionLocal()
    from app.models.verified import VerifiedLoan
    v1row = db.scalar(select(VerifiedLoan).where(VerifiedLoan.loan_pk == pk, VerifiedLoan.version == 1))
    hash1 = v1row.record_hash
    db.close()
    assert hash1 == v1["record_hash"]  # V1 immutable
    assert v2["record_hash"] != hash1  # V2 differs
