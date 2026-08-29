from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class Loan(Base):
    """Layer-2 operational: the canonical, normalized loan (21 PS §6 fields).

    Distinct from the immutable raw_record it was normalized from and from the verified
    snapshot it may later become. Dirty values that don't normalize are stored as NULL with
    a reason in `normalization_notes`; the raw cell is always preserved in raw_records.
    """

    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_file_id: Mapped[str] = mapped_column(String, ForeignKey("source_files.id"), index=True)
    raw_record_id: Mapped[str] = mapped_column(String, ForeignKey("raw_records.id"))

    # Canonical fields (nullable: dirty data is expected and flagged by validation later)
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    borrower_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    loan_type: Mapped[str | None] = mapped_column(String, nullable=True)
    origination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_principal: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    current_balance: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    interest_rate: Mapped[float | None] = mapped_column(Numeric(9, 4), nullable=True)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    borrower_state: Mapped[str | None] = mapped_column(String, nullable=True)
    loan_purpose: Mapped[str | None] = mapped_column(String, nullable=True)
    credit_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    employment_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    income_band: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    days_past_due: Mapped[int | None] = mapped_column(Integer, nullable=True)
    servicer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_status: Mapped[str | None] = mapped_column(String, nullable=True)
    source_system: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="imported", index=True)  # lifecycle state
    normalization_status: Mapped[str] = mapped_column(String, default="clean", index=True)  # clean|attention
    normalization_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    field_provenance: Mapped[list | None] = mapped_column(JSON, nullable=True)  # per-field lineage
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
