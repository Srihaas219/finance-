from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class AIAuditLog(Base):
    """Every AI call is logged here with prompt/model/provider/timestamp/latency and a hash
    of the input context (PS §9). Written whether the call succeeds or degrades."""

    __tablename__ = "ai_audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(String)
    context_hash: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIRecommendation(Base):
    """Advisory AI output. NEVER written to a canonical loan directly; a reviewer applies it
    via the review module, which is what actually mutates data (ADR-003/017). Kept separate
    from ReviewDecision."""

    __tablename__ = "ai_recommendations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    loan_pk: Mapped[str] = mapped_column(String, ForeignKey("loans.id"), index=True)
    exception_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("exceptions.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String, index=True)
    output: Mapped[dict] = mapped_column(JSON)  # schema-validated structured output
    suggested_field: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_audit_log_id: Mapped[str] = mapped_column(String, ForeignKey("ai_audit_logs.id"))
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)  # set true when a human applies it
    disposition: Mapped[str | None] = mapped_column(String, nullable=True)  # accepted|edited|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
