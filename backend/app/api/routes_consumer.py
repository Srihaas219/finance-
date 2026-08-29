from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.constants import ROLE_CONSUMER, ROLE_OPERATOR, ROLE_REVIEWER
from ..core.db import get_db
from ..models.user import User
from ..models.verified import VerifiedLoan
from ..schemas.ingestion import Page
from ..schemas.verified import VerifiedDetail, VerifiedListItem
from ..verification.trace import build_trace
from .deps import require_role

router = APIRouter(tags=["consumer"])

READERS = (ROLE_CONSUMER, ROLE_REVIEWER, ROLE_OPERATOR)


@router.get("/verified-loans", response_model=Page)
def list_verified(
    db: Session = Depends(get_db), user: User = Depends(require_role(*READERS)),
    q: str | None = Query(None), latest_only: bool = Query(True),
    limit: int = Query(50), offset: int = Query(0),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    stmt = select(VerifiedLoan)
    if latest_only:
        # newest version per loan_pk
        sub = (
            select(VerifiedLoan.loan_pk, func.max(VerifiedLoan.version).label("v"))
            .group_by(VerifiedLoan.loan_pk).subquery()
        )
        stmt = stmt.join(
            sub, (VerifiedLoan.loan_pk == sub.c.loan_pk) & (VerifiedLoan.version == sub.c.v)
        )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(VerifiedLoan.loan_id.ilike(like), VerifiedLoan.record_hash.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(VerifiedLoan.verified_at.desc()).limit(limit).offset(offset)).all()
    items = [
        VerifiedListItem(
            id=r.id, loan_pk=r.loan_pk, loan_id=r.loan_id, version=r.version,
            record_hash=r.record_hash, ai_used=r.ai_used, verified_at=r.verified_at,
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/verified-loans/{verified_id}", response_model=VerifiedDetail)
def get_verified(
    verified_id: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(*READERS)),
):
    v = db.get(VerifiedLoan, verified_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Verified record not found")
    return VerifiedDetail(
        id=v.id, loan_pk=v.loan_pk, loan_id=v.loan_id, version=v.version,
        record_hash=v.record_hash, ai_used=v.ai_used, verified_at=v.verified_at,
        snapshot=v.snapshot, validation_summary=v.validation_summary, reviewer_id=v.reviewer_id,
        supersedes_version=v.supersedes_version, ai_recommendation_ids=v.ai_recommendation_ids,
    )


@router.get("/verified-loans/{verified_id}/versions", response_model=list[VerifiedListItem])
def verified_versions(
    verified_id: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(*READERS)),
):
    v = db.get(VerifiedLoan, verified_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Verified record not found")
    rows = db.scalars(
        select(VerifiedLoan).where(VerifiedLoan.loan_pk == v.loan_pk).order_by(VerifiedLoan.version)
    ).all()
    return [
        VerifiedListItem(id=r.id, loan_pk=r.loan_pk, loan_id=r.loan_id, version=r.version,
                         record_hash=r.record_hash, ai_used=r.ai_used, verified_at=r.verified_at)
        for r in rows
    ]


@router.get("/trace/{loan_pk}")
def trace(
    loan_pk: str,
    db: Session = Depends(get_db), user: User = Depends(require_role(*READERS)),
):
    result = build_trace(db, loan_pk)
    if result is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return result


@router.get("/export")
def export_verified(
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db), user: User = Depends(require_role(ROLE_CONSUMER)),
):
    # Latest version per loan.
    sub = (
        select(VerifiedLoan.loan_pk, func.max(VerifiedLoan.version).label("v"))
        .group_by(VerifiedLoan.loan_pk).subquery()
    )
    rows = db.scalars(
        select(VerifiedLoan).join(
            sub, (VerifiedLoan.loan_pk == sub.c.loan_pk) & (VerifiedLoan.version == sub.c.v)
        ).order_by(VerifiedLoan.loan_id)
    ).all()

    from ..audit.service import build_event
    db.add(build_event(
        "verified.exported", entity_type="export", actor_id=user.id, actor_role=user.role,
        payload={"format": format, "count": len(rows)},
    ))
    db.commit()

    if format == "json":
        payload = [
            {"loan_id": r.loan_id, "version": r.version, "record_hash": r.record_hash,
             "verified_at": r.verified_at.isoformat(), "ai_used": r.ai_used, **r.snapshot}
            for r in rows
        ]
        return StreamingResponse(
            io.BytesIO(json.dumps(payload, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=verified_loans.json"},
        )

    # CSV
    from ..verification.service import SNAPSHOT_FIELDS
    meta = ["loan_id", "version", "record_hash", "verified_at", "ai_used"]
    cols = meta + [f for f in SNAPSHOT_FIELDS if f not in meta]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({"loan_id": r.loan_id, "version": r.version, "record_hash": r.record_hash,
                    "verified_at": r.verified_at.isoformat(), "ai_used": r.ai_used, **r.snapshot})
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=verified_loans.csv"},
    )
