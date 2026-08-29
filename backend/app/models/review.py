from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class ReviewDecision(Base):
    """A human reviewer action. Comments, field edits, exception dispositions, and
    loan-level approve/reject/request_correction all land here as an append-only log —
    distinct from AI recommendations (which live in ai_recommendations)."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    loan_pk: Mapped[str] = mapped_column(String, ForeignKey("loans.id"), index=True)
    exception_id: Mapped[str | None] = mapped_column(String, ForeignKey("exceptions.id"), nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String, index=True)
    # action: start_review | comment | edit_field | ignore_exception |
    #         approve | reject | request_correction | apply_ai
    action: Mapped[str] = mapped_column(String, index=True)
    field: Mapped[str | None] = mapped_column(String, nullable=True)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_recommendation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
