from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class SourceFile(Base):
    """Layer-1 evidence: one uploaded file, preserved byte-for-byte with its SHA-256.

    A re-upload of identical bytes creates a NEW logical row with `duplicate_of` set to the
    original (ADR-013) — the raw_records are not duplicated.
    """

    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    # kind: loan_tape | servicer_update | document_manifest
    kind: Mapped[str] = mapped_column(String, default="loan_tape")
    byte_size: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    duplicate_of: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
