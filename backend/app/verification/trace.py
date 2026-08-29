"""Full raw->verified traceability assembly (PS traceability money-shot).

Given a loan, return the complete lineage a judge can inspect:
VerifiedLoanVersion -> ReviewDecision -> AIRecommendation -> Exception ->
ValidationResult -> Rule -> CanonicalLoan -> FieldProvenance -> RawRecord -> SourceFile.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.ai import AIRecommendation
from ..models.loan import Loan
from ..models.raw_record import RawRecord
from ..models.review import ReviewDecision
from ..models.source_file import SourceFile
from ..models.validation import LoanException, ValidationResult
from ..models.verified import VerifiedLoan


def build_trace(db: Session, loan_pk: str) -> dict | None:
    loan = db.get(Loan, loan_pk)
    if loan is None:
        return None
    rr = db.get(RawRecord, loan.raw_record_id)
    sf = db.get(SourceFile, loan.source_file_id)

    versions = db.scalars(
        select(VerifiedLoan).where(VerifiedLoan.loan_pk == loan_pk).order_by(VerifiedLoan.version)
    ).all()
    decisions = db.scalars(
        select(ReviewDecision).where(ReviewDecision.loan_pk == loan_pk)
        .order_by(ReviewDecision.created_at)
    ).all()
    recs = db.scalars(
        select(AIRecommendation).where(AIRecommendation.loan_pk == loan_pk)
        .order_by(AIRecommendation.created_at)
    ).all()
    exceptions = db.scalars(
        select(LoanException).where(LoanException.loan_pk == loan_pk)
    ).all()
    results = db.scalars(
        select(ValidationResult).where(ValidationResult.loan_pk == loan_pk)
    ).all()

    return {
        "loan_pk": loan_pk,
        "loan_id": loan.loan_id,
        "source_file": {
            "id": sf.id, "filename": sf.filename, "file_hash": sf.file_hash,
            "uploaded_by": sf.uploaded_by,
        } if sf else None,
        "raw_record": {
            "id": rr.id, "row_number": rr.row_number, "row_hash": rr.row_hash,
            "raw_payload": rr.raw_payload,
        } if rr else None,
        "canonical_loan": {
            "status": loan.status, "normalization_status": loan.normalization_status,
        },
        "field_provenance": loan.field_provenance or [],
        "validation_results": [
            {"rule_id": r.rule_id, "severity": r.severity, "field": r.field,
             "observed_value": r.observed_value, "message": r.message}
            for r in results
        ],
        "exceptions": [
            {"id": e.id, "rule_id": e.rule_id, "severity": e.severity, "status": e.status,
             "message": e.message}
            for e in exceptions
        ],
        "ai_recommendations": [
            {"id": r.id, "kind": r.kind, "suggested_field": r.suggested_field,
             "suggested_value": r.suggested_value, "applied": r.applied,
             "disposition": r.disposition, "degraded": r.degraded}
            for r in recs
        ],
        "review_decisions": [
            {"action": d.action, "field": d.field, "old_value": d.old_value,
             "new_value": d.new_value, "comment": d.comment, "reviewer_id": d.reviewer_id,
             "ai_recommendation_id": d.ai_recommendation_id, "created_at": d.created_at.isoformat()}
            for d in decisions
        ],
        "verified_versions": [
            {"id": v.id, "version": v.version, "record_hash": v.record_hash,
             "supersedes_version": v.supersedes_version, "ai_used": v.ai_used,
             "reviewer_id": v.reviewer_id, "verified_at": v.verified_at.isoformat(),
             "snapshot": v.snapshot, "validation_summary": v.validation_summary}
            for v in versions
        ],
    }
