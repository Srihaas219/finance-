from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AIRequestIn(BaseModel):
    exception_id: str
    kind: str  # explain | suggest_correction | resolve_conflict | reviewer_note


class AIRecommendationOut(BaseModel):
    id: str
    loan_pk: str
    exception_id: str | None
    kind: str
    output: dict[str, Any]
    suggested_field: str | None
    suggested_value: str | None
    degraded: bool
    applied: bool
    disposition: str | None
    ai_audit_log_id: str
    created_at: datetime


class AIApplyIn(BaseModel):
    disposition: str  # accepted | edited | rejected
    override_value: str | None = None
    comment: str | None = None


class NLRuleIn(BaseModel):
    natural_language: str


class AIAuditLogOut(BaseModel):
    id: str
    kind: str
    provider: str
    model: str
    prompt: str
    context_hash: str
    latency_ms: int
    degraded: bool
    error: str | None
    created_at: datetime
