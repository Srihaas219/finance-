from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class VerifyOut(BaseModel):
    id: str
    loan_pk: str
    loan_id: str | None
    version: int
    record_hash: str
    supersedes_version: int | None
    ai_used: bool


class VerifiedListItem(BaseModel):
    id: str
    loan_pk: str
    loan_id: str | None
    version: int
    record_hash: str
    ai_used: bool
    verified_at: datetime


class VerifiedDetail(VerifiedListItem):
    snapshot: dict[str, Any]
    validation_summary: dict[str, Any] | None
    reviewer_id: str
    supersedes_version: int | None
    ai_recommendation_ids: list[str] | None
