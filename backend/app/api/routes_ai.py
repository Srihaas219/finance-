from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.service import apply_recommendation, generate_nl_rules, request_ai, summarize_queue
from ..core.constants import ROLE_OPERATOR, ROLE_REVIEWER
from ..core.db import get_db
from ..models.ai import AIAuditLog, AIRecommendation
from ..models.user import User
from ..review.service import NotAllowedError
from ..schemas.ai import AIApplyIn, AIAuditLogOut, AIRecommendationOut, AIRequestIn, NLRuleIn
from .deps import require_role

router = APIRouter(prefix="/ai", tags=["ai"])


def _rec_out(rec: AIRecommendation) -> AIRecommendationOut:
    return AIRecommendationOut(
        id=rec.id, loan_pk=rec.loan_pk, exception_id=rec.exception_id, kind=rec.kind,
        output=rec.output, suggested_field=rec.suggested_field, suggested_value=rec.suggested_value,
        degraded=rec.degraded, applied=rec.applied, disposition=rec.disposition,
        ai_audit_log_id=rec.ai_audit_log_id, created_at=rec.created_at,
    )


@router.post("/request", response_model=AIRecommendationOut, status_code=201)
def request(
    body: AIRequestIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    try:
        rec = request_ai(db, exception_id=body.exception_id, kind=body.kind, actor_id=user.id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'")) from None
    except NotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return _rec_out(rec)


@router.get("/recommendations/{loan_pk}", response_model=list[AIRecommendationOut])
def list_recommendations(
    loan_pk: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    rows = db.scalars(
        select(AIRecommendation).where(AIRecommendation.loan_pk == loan_pk)
        .order_by(AIRecommendation.created_at.desc())
    ).all()
    return [_rec_out(r) for r in rows]


@router.post("/recommendations/{recommendation_id}/apply")
def apply(
    recommendation_id: str, body: AIApplyIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    try:
        return apply_recommendation(
            db, recommendation_id=recommendation_id, reviewer_id=user.id,
            disposition=body.disposition, override_value=body.override_value, comment=body.comment,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'")) from None
    except NotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/summarize-queue")
def summarize(
    severity: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    """Advisory batch summary of the open exception queue (read-only, logged)."""
    return summarize_queue(db, actor_id=user.id, severity=severity)


@router.post("/nl-rule", status_code=201)
def nl_rule(
    body: NLRuleIn,
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_REVIEWER)),
):
    """Generate advisory validation rule skeletons from a natural-language description.
    Output is never applied automatically — reviewers must review and import manually."""
    return generate_nl_rules(db, natural_language=body.natural_language, actor_id=user.id)


@router.get("/logs/{log_id}", response_model=AIAuditLogOut)
def get_log(
    log_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_REVIEWER, ROLE_OPERATOR)),
):
    log = db.get(AIAuditLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="log not found")
    return log
