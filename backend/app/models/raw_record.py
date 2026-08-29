from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class RawRecord(Base):
    """Layer-1 evidence: one original CSV row, stored exactly as received. Immutable."""

    __tablename__ = "raw_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_file_id: Mapped[str] = mapped_column(String, ForeignKey("source_files.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    raw_payload: Mapped[dict] = mapped_column(JSON)  # exact original cells
    row_hash: Mapped[str] = mapped_column(String, index=True)
    import_status: Mapped[str] = mapped_column(String, default="imported")  # imported|failed
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
