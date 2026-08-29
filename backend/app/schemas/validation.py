from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ValidationRunOut(BaseModel):
    validation_run_id: str
    ruleset_version: str
    loans_evaluated: int
    totals: dict[str, Any]


class ExceptionListItem(BaseModel):
    id: str
    loan_pk: str
    loan_id: str | None
    borrower_id: str | None
    rule_id: str
    exception_type: str
    severity: str
    status: str
    field: str | None
    message: str
    version: int
    opened_at: datetime


class ExceptionDetail(ExceptionListItem):
    observed_value: str | None
    validation_run_id: str | None
    updated_at: datetime | None
    resolved_at: datetime | None
    resolved_by: str | None


class SummaryOut(BaseModel):
    uploads: int
    loans: int
    loans_with_exceptions: int
    open_exceptions: int
    exceptions_by_severity: dict[str, int]
    exceptions_by_type: dict[str, int]
    verified_loans: int
    data_quality_score: float | None
    latest_ruleset_version: str | None
