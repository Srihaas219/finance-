from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class VerifiedLoan(Base):
    """Layer-3 trusted output: an IMMUTABLE, versioned snapshot of a verified loan with a
    reproducible record hash (ADR-005/007). Never updated — a correction creates version N+1.
    """

    __tablename__ = "verified_loans"
    __table_args__ = (UniqueConstraint("loan_pk", "version", name="uq_verified_loan_version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    loan_pk: Mapped[str] = mapped_column(String, ForeignKey("loans.id"), index=True)
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)  # full canonical field set at verification
    validation_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_recommendation_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    record_hash: Mapped[str] = mapped_column(String, index=True)
    supersedes_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
