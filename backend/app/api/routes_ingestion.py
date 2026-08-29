from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.constants import ROLE_CONSUMER, ROLE_OPERATOR, ROLE_REVIEWER
from ..core.db import get_db
from ..core.hashing import sha256_hex
from ..ingestion.service import ingest_csv, ingest_servicer_csv
from ..models.audit_event import AuditEvent
from ..models.loan import Loan
from ..models.raw_record import RawRecord
from ..models.source_file import SourceFile
from ..models.user import User
from ..schemas.ingestion import (
    AuditEventOut,
    LoanDetail,
    LoanListItem,
    Page,
    UploadListItem,
    UploadSummary,
)
from .deps import require_role

router = APIRouter(tags=["ingestion"])


def _paginate(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 200)), max(0, offset)


@router.post("/uploads", response_model=UploadSummary, status_code=201)
async def upload_csv(
    file: UploadFile,
    kind: str = "loan_tape",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR)),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    safe_filename = os.path.basename(file.filename or "upload.csv") or "upload.csv"
    try:
        if kind == "servicer_update":
            result = ingest_servicer_csv(
                db, filename=safe_filename, content=content,
                uploaded_by_id=user.id, uploaded_by_role=user.role,
            )
            # normalize to the UploadSummary shape
            return {
                "id": result["id"], "filename": safe_filename,
                "kind": "servicer_update", "byte_size": len(content),
                "file_hash": sha256_hex(content),
                "duplicate": result["duplicate"], "original_upload_id": result.get("original_upload_id"),
                "row_count": result["row_count"], "imported_count": result["imported_count"],
                "failed_count": 0, "failed_samples": [],
                "note": "Servicer second-source ingested; used for source_conflict detection.",
            }
        summary = ingest_csv(
            db,
            filename=safe_filename,
            content=content,
            uploaded_by_id=user.id,
            uploaded_by_role=user.role,
            kind=kind,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return summary


@router.get("/uploads", response_model=Page)
def list_uploads(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR)),
    limit: int = Query(50), offset: int = Query(0),
):
    limit, offset = _paginate(limit, offset)
    total = db.scalar(select(func.count()).select_from(SourceFile)) or 0
    rows = db.scalars(
        select(SourceFile).order_by(SourceFile.uploaded_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        UploadListItem(
            id=r.id, filename=r.filename, kind=r.kind, row_count=r.row_count,
            imported_count=r.imported_count, failed_count=r.failed_count,
            duplicate=r.duplicate_of is not None, uploaded_at=r.uploaded_at,
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/uploads/{upload_id}", response_model=UploadSummary)
def get_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR)),
):
    sf = db.get(SourceFile, upload_id)
    if sf is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    failed = db.scalars(
        select(RawRecord)
        .where(RawRecord.source_file_id == sf.id, RawRecord.import_status == "failed")
        .limit(10)
    ).all()
    samples = [{"row_number": r.row_number, "reason": r.failure_reason or "unknown"} for r in failed]
    return UploadSummary(
        id=sf.id, filename=sf.filename, kind=sf.kind, byte_size=sf.byte_size, file_hash=sf.file_hash,
        duplicate=sf.duplicate_of is not None, original_upload_id=sf.duplicate_of,
        row_count=sf.row_count, imported_count=sf.imported_count, failed_count=sf.failed_count,
        failed_samples=samples,
    )


@router.get("/loans", response_model=Page)
def list_loans(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER)),
    source_file_id: str | None = Query(None),
    q: str | None = Query(None, description="search loan_id or borrower_id"),
    attention: bool = Query(False, description="only loans needing normalization attention"),
    limit: int = Query(50), offset: int = Query(0),
):
    limit, offset = _paginate(limit, offset)
    stmt = select(Loan)
    if source_file_id:
        stmt = stmt.where(Loan.source_file_id == source_file_id)
    if attention:
        stmt = stmt.where(Loan.normalization_status == "attention")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Loan.loan_id.ilike(like), Loan.borrower_id.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Loan.created_at.desc()).limit(limit).offset(offset)).all()
    items = [
        LoanListItem(
            id=r.id, loan_id=r.loan_id, borrower_id=r.borrower_id, payment_status=r.payment_status,
            current_balance=float(r.current_balance) if r.current_balance is not None else None,
            status=r.status, source_file_id=r.source_file_id,
            normalization_status=r.normalization_status,
            issue_fields=[
                p["field"] for p in (r.field_provenance or []) if p["status"] in ("failed", "review")
            ],
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/loans/{loan_pk}", response_model=LoanDetail)
def get_loan(
    loan_pk: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER)),
):
    loan = db.get(Loan, loan_pk)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    rr = db.get(RawRecord, loan.raw_record_id)
    sf = db.get(SourceFile, loan.source_file_id)
    provenance = {
        "source_file_id": loan.source_file_id,
        "source_filename": sf.filename if sf else None,
        "file_hash": sf.file_hash if sf else None,
        "raw_record_id": loan.raw_record_id,
        "row_number": rr.row_number if rr else None,
        "row_hash": rr.row_hash if rr else None,
        "raw_payload": rr.raw_payload if rr else None,
    }

    def num(x):
        return float(x) if x is not None else None

    return LoanDetail(
        id=loan.id, source_file_id=loan.source_file_id, raw_record_id=loan.raw_record_id,
        status=loan.status, loan_id=loan.loan_id, borrower_id=loan.borrower_id, loan_type=loan.loan_type,
        origination_date=loan.origination_date, maturity_date=loan.maturity_date,
        original_principal=num(loan.original_principal), current_balance=num(loan.current_balance),
        interest_rate=num(loan.interest_rate), term_months=loan.term_months,
        borrower_state=loan.borrower_state, loan_purpose=loan.loan_purpose, credit_grade=loan.credit_grade,
        employment_length=loan.employment_length, income_band=loan.income_band,
        payment_status=loan.payment_status, days_past_due=loan.days_past_due,
        servicer_name=loan.servicer_name,
        last_payment_date=loan.last_payment_date, last_updated_at=loan.last_updated_at,
        document_status=loan.document_status, source_system=loan.source_system,
        normalization_status=loan.normalization_status,
        normalization_notes=loan.normalization_notes,
        field_provenance=loan.field_provenance,
        provenance=provenance,
    )


@router.get("/audit/{loan_id}", response_model=list[AuditEventOut])
def get_audit(
    loan_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ROLE_OPERATOR, ROLE_REVIEWER, ROLE_CONSUMER)),
):
    rows = db.scalars(
        select(AuditEvent).where(AuditEvent.loan_id == loan_id).order_by(AuditEvent.occurred_at.asc())
    ).all()
    return rows
