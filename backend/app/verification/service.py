"""Create immutable, hashed, versioned verified snapshots — atomically (ADR-005/007/016).

A single transaction: build snapshot -> compute canonical hash -> persist version ->
audit event. Corrections after V1 create V2 (V1 stays queryable). Uses the shared
core.hashing canonicalizer (no second hash function)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit.service import build_event
from ..core.hashing import hash_record
from ..core.ids import new_id
from ..models.ai import AIRecommendation
from ..models.loan import Loan
from ..models.validation import LoanException
from ..models.verified import VerifiedLoan
from ..review.service import NotAllowedError

SNAPSHOT_FIELDS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]


def _snapshot(loan: Loan) -> dict:
    snap = {}
    for f in SNAPSHOT_FIELDS:
        v = getattr(loan, f)
        if isinstance(v, Decimal):
            snap[f] = str(v)
        elif hasattr(v, "isoformat"):
            snap[f] = v.isoformat()
        else:
            snap[f] = v
    return snap


def verify_loan(db: Session, *, loan_pk: str, reviewer_id: str) -> dict:
    loan = db.get(Loan, loan_pk)
    if loan is None:
        raise KeyError("loan not found")

    open_ex = db.scalar(
        select(LoanException).where(
            LoanException.loan_pk == loan_pk,
            LoanException.status.in_(("open", "in_review")),
        ).limit(1)
    )
    if open_ex is not None:
        raise NotAllowedError("cannot verify: loan has open exceptions")
    if loan.status not in ("approved", "clean"):
        raise NotAllowedError(f"cannot verify a loan in status '{loan.status}' (approve it first)")

    prev_version = db.scalar(
        select(func.max(VerifiedLoan.version)).where(VerifiedLoan.loan_pk == loan_pk)
    )
    version = (prev_version or 0) + 1

    snapshot = _snapshot(loan)
    ignored = db.scalars(
        select(LoanException).where(
            LoanException.loan_pk == loan_pk, LoanException.status == "ignored"
        )
    ).all()
    validation_summary = {
        "ignored_exceptions": [{"rule_id": e.rule_id, "message": e.message} for e in ignored],
        "open_exceptions": 0,
    }
    ai_recs = db.scalars(
        select(AIRecommendation).where(
            AIRecommendation.loan_pk == loan_pk, AIRecommendation.applied.is_(True)
        )
    ).all()
    ai_ids = [r.id for r in ai_recs]

    # Canonical, reproducible hash over the stable content (not volatile timestamps).
    hash_input = {"loan_id": loan.loan_id, "version": version, "snapshot": snapshot}
    record_hash = hash_record(hash_input)

    verified = VerifiedLoan(
        id=new_id(), loan_pk=loan_pk, loan_id=loan.loan_id, version=version,
        snapshot=snapshot, validation_summary=validation_summary, reviewer_id=reviewer_id,
        ai_used=bool(ai_ids), ai_recommendation_ids=ai_ids, record_hash=record_hash,
        supersedes_version=prev_version,
    )
    db.add(verified)
    loan.status = "verified"
    db.add(build_event(
        "verified.created", entity_type="verified_loan", entity_id=verified.id,
        actor_id=reviewer_id, actor_role="reviewer", loan_id=loan.loan_id,
        payload={"version": version, "record_hash": record_hash, "supersedes": prev_version,
                 "ai_used": bool(ai_ids)},
    ))
    db.commit()

    return {
        "id": verified.id, "loan_pk": loan_pk, "loan_id": loan.loan_id, "version": version,
        "record_hash": record_hash, "supersedes_version": prev_version, "ai_used": bool(ai_ids),
    }
