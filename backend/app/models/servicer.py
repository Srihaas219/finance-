from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class ServicerRecord(Base):
    """Second-source (servicer feed) values, keyed by business loan_id. Used by the
    deterministic `source_conflict` rule and by AI conflict-comparison. Normalized to match
    the canonical loan so comparisons are apples-to-apples. Immutable evidence-adjacent
    (one row per servicer_update.csv line)."""

    __tablename__ = "servicer_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_file_id: Mapped[str] = mapped_column(String, ForeignKey("source_files.id"), index=True)
    raw_record_id: Mapped[str] = mapped_column(String, ForeignKey("raw_records.id"))
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    current_balance: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String, nullable=True)
    days_past_due: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    servicer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source_system: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
