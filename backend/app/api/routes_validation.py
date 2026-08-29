from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.constants import ROLE_CONSUMER, ROLE_OPERATOR, ROLE_REVIEWER
from ..core.db import get_db
from ..models.loan import Loan
from ..models.source_file import SourceFile
from ..models.user import User
from ..models.validation import LoanException, ValidationRun
from ..schemas.ingestion import Page
from ..schemas.validation import ExceptionDetail, ExceptionListItem, SummaryOut, ValidationRunOut
from ..validation.service import run_validation
from .deps import require_role

router = APIRouter(tags=["validation"])

OPEN_STATES = ("open", "in_review")


def _verified_count(db: Session) -> int:
    """Verified-loan count; tolerant of the model not existing until migration 0006."""
    try:
        from ..models.verified import VerifiedLoan
        return db.scalar(select(func.count()).select_from(VerifiedLoan)) or 0
    except Exception:
        return 0


@router.post("/validate", response_model=ValidationRunOut, status_code=201)
def trigger_validation(
    source_file_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR)),
):
    if source_file_id and db.get(SourceFile, source_file_id) is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    result = run_validation(db, source_file_id=source_file_id, actor_id=user.id, actor_role=user.role)
    return result


@router.get("/exceptions", response_model=Page)
def list_exceptions(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER)),
    severity: str | None = Query(None),
    type: str | None = Query(None, description="exception_type / rule_id"),
    status: str | None = Query(None),
    q: str | None = Query(None, description="search loan_id or borrower_id"),
    limit: int = Query(50), offset: int = Query(0),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    stmt = select(LoanException)
    if severity:
        stmt = stmt.where(LoanException.severity == severity)
    if type:
        stmt = stmt.where(LoanException.exception_type == type)
    if status:
        stmt = stmt.where(LoanException.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(LoanException.loan_id.ilike(like), LoanException.borrower_id.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(LoanException.opened_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        ExceptionListItem(
            id=e.id, loan_pk=e.loan_pk, loan_id=e.loan_id, borrower_id=e.borrower_id,
            rule_id=e.rule_id, exception_type=e.exception_type, severity=e.severity,
            status=e.status, field=e.field, message=e.message, version=e.version,
            opened_at=e.opened_at,
        )
        for e in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/exceptions/{exception_id}", response_model=ExceptionDetail)
def get_exception(
    exception_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER)),
):
    e = db.get(LoanException, exception_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    return ExceptionDetail(
        id=e.id, loan_pk=e.loan_pk, loan_id=e.loan_id, borrower_id=e.borrower_id,
        rule_id=e.rule_id, exception_type=e.exception_type, severity=e.severity,
        status=e.status, field=e.field, message=e.message, version=e.version,
        opened_at=e.opened_at, observed_value=e.observed_value,
        validation_run_id=e.validation_run_id, updated_at=e.updated_at,
        resolved_at=e.resolved_at, resolved_by=e.resolved_by,
    )


@router.get("/summary", response_model=SummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER, ROLE_CONSUMER)),
):
    uploads = db.scalar(select(func.count()).select_from(SourceFile)) or 0
    loans = db.scalar(select(func.count()).select_from(Loan)) or 0
    open_ex = db.scalar(
        select(func.count()).select_from(LoanException).where(LoanException.status.in_(OPEN_STATES))
    ) or 0
    loans_with_ex = db.scalar(
        select(func.count(func.distinct(LoanException.loan_pk))).where(
            LoanException.status.in_(OPEN_STATES)
        )
    ) or 0
    by_sev = dict(
        db.execute(
            select(LoanException.severity, func.count())
            .where(LoanException.status.in_(OPEN_STATES))
            .group_by(LoanException.severity)
        ).all()
    )
    by_type = dict(
        db.execute(
            select(LoanException.exception_type, func.count())
            .where(LoanException.status.in_(OPEN_STATES))
            .group_by(LoanException.exception_type)
        ).all()
    )
    verified = _verified_count(db)
    latest_run = db.scalar(select(ValidationRun).order_by(ValidationRun.started_at.desc()))
    quality = round(100.0 * (loans - loans_with_ex) / loans, 1) if loans else None

    return SummaryOut(
        uploads=uploads, loans=loans, loans_with_exceptions=loans_with_ex,
        open_exceptions=open_ex, exceptions_by_severity=by_sev, exceptions_by_type=by_type,
        verified_loans=verified, data_quality_score=quality,
        latest_ruleset_version=latest_run.ruleset_version if latest_run else None,
    )
