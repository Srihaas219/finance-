"""Reviewer workbench service: exception dispositions, field edits, loan decisions.

Invariants:
- Deterministic engine owns exceptions; humans set status (in_review/ignored) and edit
  allow-listed fields, which triggers RE-VALIDATION (the engine, not the human, clears the
  exception).
- Every state change writes a ReviewDecision + an AuditEvent in one transaction (ADR-016).
- Exception writes use optimistic concurrency on `version` (ADR-015) -> 409 on stale.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import build_event
from ..core.ids import new_id
from ..ingestion.normalize import normalize_row
from ..models.loan import Loan
from ..models.review import ReviewDecision
from ..models.validation import LoanException
from ..validation.config import default_ruleset
from ..validation.service import run_validation


class ConflictError(Exception):
    """Optimistic-concurrency conflict (stale version) -> HTTP 409."""


class NotAllowedError(Exception):
    """Business-rule violation -> HTTP 400/409 depending on caller."""


EXCEPTION_TRANSITIONS = {
    "start_review": {"from": ("open",), "to": "in_review"},
    "ignore": {"from": ("open", "in_review"), "to": "ignored"},
    "reopen": {"from": ("ignored", "resolved"), "to": "open"},
}


def _bump(ex: LoanException, expected_version: int | None):
    if expected_version is not None and expected_version != ex.version:
        raise ConflictError(
            f"exception was modified by someone else (expected v{expected_version}, now v{ex.version})"
        )
    ex.version += 1
    ex.updated_at = datetime.now(UTC)


def exception_action(
    db: Session, *, exception_id: str, action: str, reviewer_id: str,
    comment: str | None = None, expected_version: int | None = None,
) -> LoanException:
    ex = db.get(LoanException, exception_id)
    if ex is None:
        raise KeyError("exception not found")
    spec = EXCEPTION_TRANSITIONS.get(action)
    if spec is None:
        raise NotAllowedError(f"unknown exception action '{action}'")
    if ex.status not in spec["from"]:
        raise NotAllowedError(f"cannot '{action}' an exception in status '{ex.status}'")

    _bump(ex, expected_version)
    ex.status = spec["to"]
    if spec["to"] == "ignored":
        ex.resolved_by = reviewer_id
        ex.resolved_at = datetime.now(UTC)

    db.add(ReviewDecision(
        id=new_id(), loan_pk=ex.loan_pk, exception_id=ex.id, reviewer_id=reviewer_id,
        action=f"{action}_exception" if action != "start_review" else "start_review",
        comment=comment,
    ))
    db.add(build_event(
        f"exception.{action}", entity_type="exception", entity_id=ex.id,
        actor_id=reviewer_id, actor_role="reviewer", loan_id=ex.loan_id,
        payload={"status": ex.status, "rule_id": ex.rule_id, "comment": comment},
    ))
    db.commit()
    return ex


def add_comment(db: Session, *, loan_pk: str, reviewer_id: str, comment: str,
                exception_id: str | None = None) -> ReviewDecision:
    loan = db.get(Loan, loan_pk)
    if loan is None:
        raise KeyError("loan not found")
    rd = ReviewDecision(
        id=new_id(), loan_pk=loan_pk, exception_id=exception_id, reviewer_id=reviewer_id,
        action="comment", comment=comment,
    )
    db.add(rd)
    db.add(build_event(
        "comment.added", entity_type="loan", entity_id=loan_pk, actor_id=reviewer_id,
        actor_role="reviewer", loan_id=loan.loan_id, payload={"comment": comment},
    ))
    db.commit()
    return rd


def edit_field(db: Session, *, loan_pk: str, reviewer_id: str, field: str, value: str,
               comment: str | None = None) -> dict:
    loan = db.get(Loan, loan_pk)
    if loan is None:
        raise KeyError("loan not found")
    rs = default_ruleset()
    if field not in rs.allowed_edit_fields:
        raise NotAllowedError(f"field '{field}' is not editable (allowed: {sorted(rs.allowed_edit_fields)})")

    old = getattr(loan, field)
    canonical, _notes = normalize_row({field: value})  # deterministic coercion, same as ingestion
    coerced = canonical[field]
    setattr(loan, field, coerced)

    db.add(ReviewDecision(
        id=new_id(), loan_pk=loan_pk, reviewer_id=reviewer_id, action="edit_field",
        field=field, old_value=str(old) if old is not None else None,
        new_value=str(coerced) if coerced is not None else None, comment=comment,
    ))
    db.add(build_event(
        "field.edited", entity_type="loan", entity_id=loan_pk, actor_id=reviewer_id,
        actor_role="reviewer", loan_id=loan.loan_id,
        payload={"field": field, "old": str(old), "new": str(coerced), "comment": comment},
    ))
    db.commit()

    # Re-validation is what actually clears/refreshes exceptions (engine is source of truth).
    run_validation(db, source_file_id=loan.source_file_id, actor_id=reviewer_id, actor_role="reviewer")
    return {"field": field, "old": str(old) if old is not None else None,
            "new": str(coerced) if coerced is not None else None}


def loan_decision(db: Session, *, loan_pk: str, reviewer_id: str, action: str,
                  comment: str | None = None) -> Loan:
    loan = db.get(Loan, loan_pk)
    if loan is None:
        raise KeyError("loan not found")
    if action not in ("approve", "reject", "request_correction"):
        raise NotAllowedError(f"unknown loan decision '{action}'")

    if action == "approve":
        open_ct = db.scalar(
            select(LoanException).where(
                LoanException.loan_pk == loan_pk,
                LoanException.status.in_(("open", "in_review")),
            ).limit(1)
        )
        if open_ct is not None:
            raise NotAllowedError("cannot approve: loan still has open exceptions (resolve or ignore first)")
        loan.status = "approved"
    elif action == "reject":
        loan.status = "rejected"
    else:
        loan.status = "correction_requested"

    db.add(ReviewDecision(
        id=new_id(), loan_pk=loan_pk, reviewer_id=reviewer_id, action=action, comment=comment,
    ))
    db.add(build_event(
        f"loan.{action}", entity_type="loan", entity_id=loan_pk, actor_id=reviewer_id,
        actor_role="reviewer", loan_id=loan.loan_id, payload={"status": loan.status, "comment": comment},
    ))
    db.commit()
    return loan
