"""Persist a validation run: results + upserted exceptions, in one transaction.

State-machine note (ADR-014): exceptions are unique on (loan_pk, rule_id). Re-running
upserts — a still-failing rule keeps its exception, a newly-failing rule creates one, and
an exception that no longer fails is auto-resolved (status open/in_review -> resolved by
rerun). `ignored` and already-`resolved` exceptions are left untouched.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import build_event
from ..core.ids import new_id
from ..models.loan import Loan
from ..models.servicer import ServicerRecord
from ..models.validation import LoanException, ValidationResult, ValidationRun
from .config import Ruleset, default_ruleset
from .engine import loan_to_view, run_rules


def _load_servicer_map(db: Session) -> dict[str, dict]:
    """Latest servicer record per loan_id, normalized to strings for comparison."""
    rows = db.scalars(select(ServicerRecord).order_by(ServicerRecord.created_at)).all()
    out: dict[str, dict] = {}
    for r in rows:
        if not r.loan_id:
            continue
        out[r.loan_id] = {  # later rows overwrite -> "latest"
            "current_balance": str(r.current_balance) if r.current_balance is not None else None,
            "payment_status": r.payment_status,
            "days_past_due": r.days_past_due,
            "last_updated_at": r.last_updated_at.isoformat() if r.last_updated_at else "",
        }
    return out


def run_validation(
    db: Session,
    *,
    source_file_id: str | None = None,
    actor_id: str | None = None,
    actor_role: str = "system",
    ruleset: Ruleset | None = None,
) -> dict:
    rs = ruleset or default_ruleset()

    stmt = select(Loan)
    if source_file_id:
        stmt = stmt.where(Loan.source_file_id == source_file_id)
    loans = db.scalars(stmt).all()
    views = [loan_to_view(loan) for loan in loans]
    loan_by_pk = {loan.id: loan for loan in loans}

    # Build the servicer map (latest record per loan_id) so `source_conflict` can fire.
    servicer_by_loan_id = _load_servicer_map(db)

    findings = run_rules(views, rs, servicer_by_loan_id=servicer_by_loan_id)

    run = ValidationRun(
        id=new_id(),
        source_file_id=source_file_id,
        ruleset_version=rs.version,
        status="running",
        loans_evaluated=len(loans),
    )
    db.add(run)
    db.flush()

    # Existing exceptions for the evaluated loans, keyed by (loan_pk, rule_id, field).
    existing = {}
    if loan_by_pk:
        rows = db.scalars(
            select(LoanException).where(LoanException.loan_pk.in_(list(loan_by_pk.keys())))
        ).all()
        for e in rows:
            existing[(e.loan_pk, e.rule_id, e.field)] = e

    now = datetime.now(UTC)
    type_counts: Counter = Counter()
    sev_counts: Counter = Counter()
    created = updated = resolved = 0
    seen_keys: set[tuple[str, str, str | None]] = set()

    for pk, fs in findings.items():
        loan = loan_by_pk[pk]
        for f in fs:
            key = (pk, f.rule_id, f.field)
            seen_keys.add(key)
            type_counts[f.rule_id] += 1
            sev_counts[f.severity] += 1

            db.add(ValidationResult(
                id=new_id(), validation_run_id=run.id, loan_pk=pk, loan_id=loan.loan_id,
                rule_id=f.rule_id, severity=f.severity, field=f.field,
                observed_value=f.observed_value, message=f.message,
            ))

            ex = existing.get(key)
            if ex is None:
                db.add(LoanException(
                    id=new_id(), loan_pk=pk, loan_id=loan.loan_id, borrower_id=loan.borrower_id,
                    rule_id=f.rule_id, exception_type=f.rule_id, severity=f.severity,
                    status="open", field=f.field, observed_value=f.observed_value,
                    message=f.message, validation_run_id=run.id, version=1, opened_at=now,
                ))
                created += 1
            elif ex.status in ("open", "in_review"):
                # refresh details; keep human status
                ex.severity = f.severity
                ex.observed_value = f.observed_value
                ex.message = f.message
                ex.validation_run_id = run.id
                ex.updated_at = now
                updated += 1

    # Auto-resolve exceptions that no longer fail (only open/in_review).
    for key, ex in existing.items():
        if key not in seen_keys and ex.status in ("open", "in_review"):
            ex.status = "resolved"
            ex.resolved_at = now
            ex.resolved_by = "system:rerun"
            ex.updated_at = now
            resolved += 1

    # Flush so the newly-added/updated exceptions are visible to the status query below.
    # (SessionLocal uses autoflush=False, so this is required for a correct loan.status.)
    db.flush()

    # Mark loans clean/exception based on current open exceptions.
    open_by_loan: set[str] = set()
    for e in db.scalars(
        select(LoanException).where(
            LoanException.loan_pk.in_(list(loan_by_pk.keys())),
            LoanException.status.in_(("open", "in_review")),
        )
    ).all() if loan_by_pk else []:
        open_by_loan.add(e.loan_pk)
    for loan in loans:
        loan.status = "exception" if loan.id in open_by_loan else "clean"

    totals = {
        "by_type": dict(type_counts),
        "by_severity": dict(sev_counts),
        "loans_with_exceptions": len(open_by_loan),
        "created": created, "updated": updated, "resolved": resolved,
    }
    run.totals = totals
    run.status = "completed"
    run.finished_at = now

    db.add(build_event(
        "validation.executed", entity_type="validation_run", entity_id=run.id,
        actor_id=actor_id, actor_role=actor_role, source_file_id=source_file_id,
        payload={"ruleset_version": rs.version, "loans": len(loans), **totals},
    ))
    db.commit()

    return {
        "validation_run_id": run.id,
        "ruleset_version": rs.version,
        "loans_evaluated": len(loans),
        "totals": totals,
    }
