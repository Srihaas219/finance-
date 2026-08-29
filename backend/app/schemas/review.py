from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ExceptionActionIn(BaseModel):
    action: str  # start_review | ignore | reopen
    comment: str | None = None
    expected_version: int | None = None


class CommentIn(BaseModel):
    comment: str
    exception_id: str | None = None


class FieldEditIn(BaseModel):
    field: str
    value: str
    comment: str | None = None


class LoanDecisionIn(BaseModel):
    action: str  # approve | reject | request_correction
    comment: str | None = None


class ReviewDecisionOut(BaseModel):
    id: str
    loan_pk: str
    exception_id: str | None
    reviewer_id: str
    action: str
    field: str | None
    old_value: str | None
    new_value: str | None
    comment: str | None
    created_at: datetime
