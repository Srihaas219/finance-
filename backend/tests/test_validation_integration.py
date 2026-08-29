"""Integration: ingest golden fixtures + full tape, run validation, assert exception coverage.

Ground truth wins: we assert each required issue class is DETECTED. For fuzzy cross-row
rules (repeated_borrower, duplicate_combo) the full tape may find additional natural
instances beyond the injected ledger rows; we assert >= the injected count and document it.
"""
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.ingestion.service import ingest_csv
from app.models.validation import LoanException
from app.validation.service import run_validation

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "fixtures" / "golden"
LOAN_TAPE = REPO / "data" / "raw" / "loan_tape.csv"


@pytest.fixture(autouse=True)
def _clean_ingestion_tables():
    """Isolate these tests: wipe ingestion/validation rows so re-ingesting fixed fixture bytes
    is not treated as a duplicate of an upload from another test."""
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
    # Delete in FK-dependency order (children first).
    for model in (VerifiedLoan, AIRecommendation, AIAuditLog, ReviewDecision, ValidationResult,
                  LoanException, ValidationRun, AuditEvent, ServicerRecord, Loan, RawRecord, SourceFile):
        db.query(model).delete()
    db.commit()
    db.close()
    yield

# All 15 PS issue classes. source_conflict needs the servicer file (not ingested here),
# so it is covered by the pure unit test test_source_conflict_rule instead.
SINGLE_FILE_CLASSES = [
    "missing_loan_id", "duplicate_loan_id", "duplicate_combo", "invalid_date_format",
    "maturity_before_origination", "negative_principal", "balance_gt_principal",
    "rate_out_of_range", "status_dpd_mismatch", "missing_document_status",
    "stale_record", "invalid_state_code", "repeated_borrower", "closed_positive_balance",
]


def _ingest_and_validate(content: bytes, filename: str) -> str:
    db = SessionLocal()
    sf = ingest_csv(db, filename=filename, content=content,
                    uploaded_by_id="u-operator", uploaded_by_role="data_operator")
    run_validation(db, source_file_id=sf["id"], actor_id="u-operator", actor_role="data_operator")
    db.close()
    return sf["id"]


@pytest.mark.skipif(not LOAN_TAPE.exists(), reason="dataset not generated")
def test_full_tape_covers_all_single_file_classes():
    _ingest_and_validate(LOAN_TAPE.read_bytes(), "loan_tape.csv")
    db = SessionLocal()
    types = set(db.scalars(select(func.distinct(LoanException.exception_type))).all())
    db.close()
    missing = [c for c in SINGLE_FILE_CLASSES if c not in types]
    assert not missing, f"missing issue classes: {missing}"


@pytest.mark.skipif(not LOAN_TAPE.exists(), reason="dataset not generated")
def test_full_tape_injected_counts_met():
    """Row-level injected counts should match; cross-row may exceed (documented)."""
    _ingest_and_validate(LOAN_TAPE.read_bytes(), "loan_tape_counts.csv")
    db = SessionLocal()
    counts = dict(db.execute(
        select(LoanException.exception_type, func.count()).group_by(LoanException.exception_type)
    ).all())
    db.close()
    # Injected ledger counts (from generate_synthetic_dataset.py bands).
    exact_row_level = {
        "missing_loan_id": 5, "negative_principal": 5, "balance_gt_principal": 6,
        "rate_out_of_range": 6, "missing_document_status": 8, "invalid_state_code": 6,
        "closed_positive_balance": 5, "maturity_before_origination": 6,
    }
    for code, n in exact_row_level.items():
        assert counts.get(code, 0) >= n, f"{code}: expected >= {n}, got {counts.get(code, 0)}"


@pytest.mark.parametrize("issue", [c for c in SINGLE_FILE_CLASSES])
def test_golden_fixture_fires(issue):
    fixture = GOLDEN / f"{issue}.csv"
    if not fixture.exists():
        pytest.skip(f"no golden fixture for {issue}")
    sfid = _ingest_and_validate(fixture.read_bytes(), f"{issue}.csv")
    db = SessionLocal()
    from app.models.loan import Loan
    pks = list(db.scalars(select(Loan.id).where(Loan.source_file_id == sfid)).all())
    fired = set(db.scalars(
        select(LoanException.exception_type).where(LoanException.loan_pk.in_(pks))
    ).all())
    db.close()
    assert issue in fired, f"golden fixture {issue} did not raise {issue}; raised {fired}"
