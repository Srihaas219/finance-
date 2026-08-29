from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.constants import ROLE_REVIEWER
from ..core.db import get_db
from ..models.review import ReviewDecision
from ..models.user import User
from ..review.service import (
    ConflictError,
    NotAllowedError,
    add_comment,
    edit_field,
    exception_action,
    loan_decision,
)
from ..schemas.review import (
    CommentIn,
    ExceptionActionIn,
    FieldEditIn,
    LoanDecisionIn,
    ReviewDecisionOut,
)
from ..schemas.verified import VerifyOut
from ..verification.service import verify_loan
from .deps import require_role

router = APIRouter(tags=["review"])


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except NotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'")) from None


@router.post("/exceptions/{exception_id}/review")
def review_exception(
    exception_id: str, body: ExceptionActionIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    ex = _handle(
        exception_action, db, exception_id=exception_id, action=body.action,
        reviewer_id=user.id, comment=body.comment, expected_version=body.expected_version,
    )
    return {"id": ex.id, "status": ex.status, "version": ex.version}


@router.post("/loans/{loan_pk}/comments", response_model=ReviewDecisionOut, status_code=201)
def comment(
    loan_pk: str, body: CommentIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    rd = _handle(add_comment, db, loan_pk=loan_pk, reviewer_id=user.id,
                 comment=body.comment, exception_id=body.exception_id)
    return rd


@router.patch("/loans/{loan_pk}/fields")
def patch_field(
    loan_pk: str, body: FieldEditIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    return _handle(edit_field, db, loan_pk=loan_pk, reviewer_id=user.id,
                   field=body.field, value=body.value, comment=body.comment)


@router.post("/loans/{loan_pk}/decision")
def decide(
    loan_pk: str, body: LoanDecisionIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    loan = _handle(loan_decision, db, loan_pk=loan_pk, reviewer_id=user.id,
                   action=body.action, comment=body.comment)
    return {"loan_pk": loan.id, "status": loan.status}


@router.post("/loans/{loan_pk}/verify", response_model=VerifyOut, status_code=201)
def verify(
    loan_pk: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    return _handle(verify_loan, db, loan_pk=loan_pk, reviewer_id=user.id)


@router.get("/loans/{loan_pk}/history", response_model=list[ReviewDecisionOut])
def loan_history(
    loan_pk: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    rows = db.scalars(
        select(ReviewDecision).where(ReviewDecision.loan_pk == loan_pk)
        .order_by(ReviewDecision.created_at.asc())
    ).all()
    return rows
