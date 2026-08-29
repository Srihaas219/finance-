from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..core.db import Base


class AuditEvent(Base):
    """Append-only audit trail. Never updated or deleted. Written in the same transaction as
    the state change it describes (ADR-008/016)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)  # or 'system'
    loan_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)  # business loan_id
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_file_id: Mapped[str | None] = mapped_column(String, ForeignKey("source_files.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
