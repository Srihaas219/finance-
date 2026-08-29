from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class ValidationRun(Base):
    """One execution of the rule engine over a set of loans (ADR-014). Versioned & reproducible."""

    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("source_files.id"), nullable=True, index=True
    )
    ruleset_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="completed")  # running|completed|failed
    loans_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    totals: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # counts by severity/type
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ValidationResult(Base):
    """A single failing rule outcome within a run (passing rules are not stored; run totals
    capture pass counts). Structured, not string-only."""

    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    validation_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("validation_runs.id"), index=True
    )
    loan_pk: Mapped[str] = mapped_column(String, ForeignKey("loans.id"), index=True)
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String)
    field: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_value: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String)


class LoanException(Base):
    """An open data-quality issue on a loan, created only by the deterministic engine.

    Unique on (loan_pk, rule_id): re-running validation upserts rather than duplicating
    (ADR-014). `version` is an optimistic-concurrency guard for reviewer writes (ADR-015)."""

    __tablename__ = "exceptions"
    # (loan_pk, rule_id, field): a rule can fire on multiple fields of one loan (e.g.
    # source_conflict on both current_balance and payment_status) -> distinct exceptions.
    __table_args__ = (UniqueConstraint("loan_pk", "rule_id", "field", name="uq_exception_loan_rule_field"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    loan_pk: Mapped[str] = mapped_column(String, ForeignKey("loans.id"), index=True)
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    borrower_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    exception_type: Mapped[str] = mapped_column(String, index=True)  # == rule_id (readable alias)
    severity: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="open", index=True)  # open|in_review|resolved|ignored
    field: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_value: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String)
    validation_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic lock
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
