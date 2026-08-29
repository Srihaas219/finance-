"""AI orchestration: Exception -> evidence -> provider -> schema-validated -> AIRecommendation.

Boundary (ADR-003/017): AI output is advisory and stored separately. Applying a suggestion
routes through review.edit_field (a human decision that mutates data); AI never writes
canonical loans. Provider failures / malformed output degrade gracefully and are logged.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import build_event
from ..core.config import get_settings
from ..core.hashing import canonical_json, sha256_hex
from ..core.ids import new_id
from ..models.ai import AIAuditLog, AIRecommendation
from ..models.loan import Loan
from ..models.review import ReviewDecision
from ..models.validation import LoanException
from ..review.service import NotAllowedError, edit_field
from .provider import AIProvider, get_ai_provider

_CANONICAL_FOR_EVIDENCE = (
    "loan_id", "borrower_id", "original_principal", "current_balance", "interest_rate",
    "origination_date", "maturity_date", "payment_status", "days_past_due",
    "borrower_state", "document_status", "last_updated_at",
)


# ---- output schemas (validate provider output; malformed -> degraded) ----
class ExplainOut(BaseModel):
    kind: str
    explanation: str
    severity_opinion: str | None = None
    evidence: list[str] = []


class SuggestOut(BaseModel):
    kind: str
    field: str | None = None
    current_value: str | None = None
    suggested_value: str | None = None
    rationale: str
    confidence: str | None = None


class ConflictOut(BaseModel):
    kind: str
    field: str | None = None
    values: list[dict] = []
    recommended_value: str | None = None
    rationale: str


class NoteOut(BaseModel):
    kind: str
    note: str


class ClassifySeverityOut(BaseModel):
    kind: str
    deterministic_severity: str
    suggested_severity: str
    agrees_with_engine: bool
    rationale: str
    advisory: bool = True
    note: str | None = None


class NLRuleOut(BaseModel):
    kind: str
    natural_language_input: str
    generated_rules: list[dict]
    explanation: str
    advisory: bool = True
    note: str | None = None


_SCHEMAS = {
    "explain": ExplainOut,
    "suggest_correction": SuggestOut,
    "resolve_conflict": ConflictOut,
    "reviewer_note": NoteOut,
    "classify_severity": ClassifySeverityOut,
    "nl_rule_generation": NLRuleOut,
}


def build_evidence(db: Session, exception: LoanException) -> dict[str, Any]:
    """Assemble the LIMITED relevant context for the model (never the whole DB)."""
    loan = db.get(Loan, exception.loan_pk)
    loan_ctx = {}
    if loan is not None:
        for f in _CANONICAL_FOR_EVIDENCE:
            v = getattr(loan, f)
            loan_ctx[f] = str(v) if v is not None else None
    ctx: dict[str, Any] = {
        "rule_id": exception.rule_id,
        "field": exception.field,
        "observed_value": exception.observed_value,
        "severity": exception.severity,
        "message": exception.message,
        "loan": loan_ctx,
    }
    # For source conflicts, attach both sources' values so the model can compare (advisory).
    if exception.rule_id == "source_conflict" and loan is not None:
        from ..models.servicer import ServicerRecord
        sr = db.scalar(
            select(ServicerRecord).where(ServicerRecord.loan_id == loan.loan_id)
            .order_by(ServicerRecord.created_at.desc())
        )
        field = exception.field or "current_balance"
        base_field = field.split("/")[0]
        loan_val = getattr(loan, base_field, None)
        srv_val = getattr(sr, base_field, None) if sr else None
        ctx["field"] = base_field
        ctx["values"] = [
            {"source": "loan_tape", "value": str(loan_val) if loan_val is not None else None,
             "last_updated_at": loan.last_updated_at.isoformat() if loan.last_updated_at else ""},
            {"source": "servicer_feed", "value": str(srv_val) if srv_val is not None else None,
             "last_updated_at": sr.last_updated_at.isoformat() if sr and sr.last_updated_at else ""},
        ]
    return ctx


def request_ai(
    db: Session, *, exception_id: str, kind: str, actor_id: str,
    provider: AIProvider | None = None,
) -> AIRecommendation:
    ex = db.get(LoanException, exception_id)
    if ex is None:
        raise KeyError("exception not found")
    if kind not in _SCHEMAS:
        raise NotAllowedError(f"unknown AI kind '{kind}'")

    provider = provider or get_ai_provider(get_settings())
    context = build_evidence(db, ex)
    context_hash = sha256_hex(canonical_json(context))

    degraded = False
    error = None
    output: dict = {}
    suggested_field = suggested_value = None
    latency = 0
    prompt = f"[{kind}]"
    model = provider.model
    pname = provider.name

    try:
        result = provider.generate(kind, context)
        latency = result.latency_ms
        prompt = result.prompt
        # Validate the shape; malformed -> treated as degraded (ADR-017).
        _SCHEMAS[kind](**result.output)
        output = result.output
        suggested_field = result.suggested_field
        suggested_value = result.suggested_value
    except (ValidationError, Exception) as e:  # noqa: BLE001 (any provider failure degrades)
        degraded = True
        error = f"{type(e).__name__}: {e}"
        output = {
            "kind": kind,
            "degraded": True,
            "message": "AI assistance is temporarily unavailable. Continue reviewing manually.",
        }

    log = AIAuditLog(
        id=new_id(), kind=kind, provider=pname, model=model, prompt=prompt,
        context_hash=context_hash, latency_ms=latency, degraded=degraded,
        error=error, actor_id=actor_id,
    )
    db.add(log)
    db.flush()

    rec = AIRecommendation(
        id=new_id(), loan_pk=ex.loan_pk, exception_id=ex.id, kind=kind, output=output,
        suggested_field=suggested_field, suggested_value=suggested_value,
        ai_audit_log_id=log.id, degraded=degraded,
    )
    db.add(rec)
    db.add(build_event(
        "ai.recommendation.generated", entity_type="ai_recommendation", entity_id=rec.id,
        actor_id=actor_id, actor_role="reviewer", loan_id=ex.loan_id,
        payload={"kind": kind, "degraded": degraded, "rule_id": ex.rule_id,
                 "ai_audit_log_id": log.id},
    ))
    db.commit()
    return rec


def summarize_queue(db: Session, *, actor_id: str, severity: str | None = None,
                    provider: AIProvider | None = None) -> dict:
    """Advisory batch summary of the OPEN exception queue. Computes deterministic stats
    (authoritative), then adds an AI narrative (Mock). Read-only — mutates nothing; logged."""
    from collections import Counter

    from ..models.validation import LoanException

    provider = provider or get_ai_provider(get_settings())
    stmt = select(LoanException).where(LoanException.status.in_(("open", "in_review")))
    if severity:
        stmt = stmt.where(LoanException.severity == severity)
    rows = db.scalars(stmt).all()

    by_sev: Counter = Counter(e.severity for e in rows)
    by_rule: Counter = Counter(e.exception_type for e in rows)
    by_field: Counter = Counter(e.field for e in rows if e.field)
    stats = {
        "total": len(rows),
        "by_severity": dict(by_sev),
        "top_rules": by_rule.most_common(5),
        "top_fields": by_field.most_common(5),
        "source_conflicts": by_rule.get("source_conflict", 0),
        "affected_loans": len({e.loan_pk for e in rows}),
    }

    degraded = False
    narrative = None
    priority = "high" if by_sev.get("high") else ("medium" if by_sev.get("medium") else "low")
    try:
        result = provider.generate("batch_summary", {"stats": stats})
        narrative = result.output.get("narrative")
        priority = result.output.get("priority", priority)
        model, pname, prompt = result.model, result.provider, result.prompt
        latency = result.latency_ms
    except Exception:  # noqa: BLE001 (any provider failure degrades; stats remain authoritative)
        degraded = True
        narrative = "AI narrative unavailable; deterministic stats below are authoritative."
        model, pname, prompt, latency = "n/a", getattr(provider, "name", "unknown"), "[batch_summary]", 0

    log = AIAuditLog(
        id=new_id(), kind="batch_summary", provider=pname, model=model, prompt=prompt,
        context_hash=sha256_hex(canonical_json(stats)), latency_ms=latency,
        degraded=degraded, actor_id=actor_id,
    )
    db.add(log)
    db.add(build_event(
        "ai.recommendation.generated", entity_type="ai_batch_summary", entity_id=log.id,
        actor_id=actor_id, actor_role="reviewer",
        payload={"kind": "batch_summary", "total": stats["total"], "degraded": degraded},
    ))
    db.commit()
    return {"stats": stats, "narrative": narrative, "priority": priority,
            "degraded": degraded, "ai_audit_log_id": log.id}


def apply_recommendation(
    db: Session, *, recommendation_id: str, reviewer_id: str, disposition: str,
    override_value: str | None = None, comment: str | None = None,
) -> dict:
    """Reviewer accepts/edits/rejects an AI suggestion. Accept/edit -> route through
    review.edit_field (the HUMAN mutates data); reject -> no mutation. Always audited."""
    rec = db.get(AIRecommendation, recommendation_id)
    if rec is None:
        raise KeyError("recommendation not found")
    if disposition not in ("accepted", "edited", "rejected"):
        raise NotAllowedError("disposition must be accepted|edited|rejected")

    rec.disposition = disposition
    if disposition == "rejected":
        rec.applied = False
        db.add(ReviewDecision(
            id=new_id(), loan_pk=rec.loan_pk, exception_id=rec.exception_id,
            reviewer_id=reviewer_id, action="apply_ai", comment=comment or "rejected AI suggestion",
            ai_recommendation_id=rec.id,
        ))
        db.add(build_event(
            "ai.recommendation.rejected", entity_type="ai_recommendation", entity_id=rec.id,
            actor_id=reviewer_id, actor_role="reviewer",
            payload={"disposition": disposition},
        ))
        db.commit()
        return {"applied": False, "disposition": disposition}

    # accepted or edited -> apply a value through the human review path
    field = rec.suggested_field
    value = override_value if disposition == "edited" else rec.suggested_value
    if not field or value is None:
        raise NotAllowedError("this recommendation has no applicable field/value to apply")

    rec.applied = True
    db.add(build_event(
        "ai.recommendation.applied", entity_type="ai_recommendation", entity_id=rec.id,
        actor_id=reviewer_id, actor_role="reviewer",
        payload={"disposition": disposition, "field": field, "value": value},
    ))
    # Record the AI linkage, then perform the human edit (which re-validates).
    db.add(ReviewDecision(
        id=new_id(), loan_pk=rec.loan_pk, exception_id=rec.exception_id,
        reviewer_id=reviewer_id, action="apply_ai", field=field, new_value=value,
        comment=comment, ai_recommendation_id=rec.id,
    ))
    db.commit()
    edit_field(db, loan_pk=rec.loan_pk, reviewer_id=reviewer_id, field=field, value=value,
               comment=f"applied AI suggestion ({disposition})")
    return {"applied": True, "disposition": disposition, "field": field, "value": value}


def generate_nl_rules(
    db: Session, *, natural_language: str, actor_id: str,
    provider: AIProvider | None = None,
) -> dict:
    """Generate validation rule skeletons from a natural-language description.

    Advisory only — output is never applied automatically to validation_rules.json.
    Always logged in ai_audit_logs.
    """
    provider = provider or get_ai_provider(get_settings())
    context = {"natural_language": natural_language, "kind": "nl_rule_generation"}
    context_hash = sha256_hex(canonical_json({"nl": natural_language[:200]}))

    degraded = False
    try:
        result = provider.generate("nl_rule_generation", context)
        output = result.output
        model, pname, prompt = result.model, result.provider, result.prompt
        latency = result.latency_ms
    except Exception:  # noqa: BLE001
        degraded = True
        output = {"kind": "nl_rule_generation", "generated_rules": [],
                  "explanation": "AI unavailable — rule generation degraded.", "advisory": True}
        model, pname, prompt, latency = "n/a", getattr(provider, "name", "unknown"), "[nl_rule_generation]", 0

    log = AIAuditLog(
        id=new_id(), kind="nl_rule_generation", provider=pname, model=model, prompt=prompt,
        context_hash=context_hash, latency_ms=latency, degraded=degraded, actor_id=actor_id,
    )
    db.add(log)
    db.add(build_event(
        "ai.recommendation.generated", entity_type="ai_nl_rule",
        entity_id=log.id, actor_id=actor_id, actor_role="reviewer",
        payload={"kind": "nl_rule_generation", "degraded": degraded},
    ))
    db.commit()

    return {
        "output": output,
        "degraded": degraded,
        "ai_audit_log_id": log.id,
    }
