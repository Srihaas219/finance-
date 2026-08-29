"""Role-gated dashboard summaries. Slice 0 returns placeholders; later slices fill them
with real ingestion / exception / verified-record data."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.constants import ROLE_CONSUMER, ROLE_OPERATOR, ROLE_REVIEWER
from ..core.db import get_db
from ..models.loan import Loan
from ..models.source_file import SourceFile
from ..models.user import User
from ..models.validation import LoanException
from .deps import require_role

router = APIRouter(tags=["dashboard"])


@router.get("/operator/summary")
def operator_summary(db: Session = Depends(get_db), _: User = Depends(require_role(ROLE_OPERATOR))):
    uploads = db.scalar(select(func.count()).select_from(SourceFile)) or 0
    imported = db.scalar(select(func.count()).select_from(Loan)) or 0
    needs_attention = db.scalar(
        select(func.count()).select_from(Loan).where(Loan.normalization_status == "attention")
    ) or 0
    corrections = db.scalar(
        select(func.count(func.distinct(LoanException.loan_pk))).where(
            LoanException.status.in_(("open", "in_review"))
        )
    ) or 0
    return {
        "role": ROLE_OPERATOR,
        "uploads": uploads,
        "records_imported": imported,
        "needs_attention": needs_attention,  # normalization: failed/flagged fields
        "corrections_needed": corrections,  # loans with open validation exceptions
        "message": "Upload a loan tape to ingest and preserve raw records.",
    }


@router.get("/reviewer/summary")
def reviewer_summary(db: Session = Depends(get_db), _: User = Depends(require_role(ROLE_REVIEWER))):
    open_ex = db.scalar(
        select(func.count()).select_from(LoanException).where(LoanException.status == "open")
    ) or 0
    in_review = db.scalar(
        select(func.count()).select_from(LoanException).where(LoanException.status == "in_review")
    ) or 0
    return {
        "role": ROLE_REVIEWER,
        "open_exceptions": open_ex,
        "in_review_exceptions": in_review,
        "message": "Review exception queue; AI assistance is advisory only.",
    }


@router.get("/consumer/summary")
def consumer_summary(db: Session = Depends(get_db), _: User = Depends(require_role(ROLE_CONSUMER))):
    from ..models.verified import VerifiedLoan

    loans = db.scalar(select(func.count()).select_from(Loan)) or 0
    loans_with_ex = db.scalar(
        select(func.count(func.distinct(LoanException.loan_pk))).where(
            LoanException.status.in_(("open", "in_review"))
        )
    ) or 0
    verified = db.scalar(
        select(func.count(func.distinct(VerifiedLoan.loan_pk)))
    ) or 0
    quality = round(100.0 * (loans - loans_with_ex) / loans, 1) if loans else None
    return {
        "role": ROLE_CONSUMER,
        "verified_loans": verified,
        "quality_score": quality,
        "message": "Browse verified records, inspect traceability, and export.",
    }
