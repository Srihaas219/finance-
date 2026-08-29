from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class FailedRow(BaseModel):
    row_number: int
    reason: str


class UploadSummary(BaseModel):
    id: str
    filename: str
    kind: str
    byte_size: int
    file_hash: str
    duplicate: bool
    original_upload_id: str | None = None
    row_count: int
    imported_count: int
    failed_count: int
    failed_samples: list[FailedRow] = []
    note: str | None = None


class UploadListItem(BaseModel):
    id: str
    filename: str
    kind: str
    row_count: int
    imported_count: int
    failed_count: int
    duplicate: bool
    uploaded_at: datetime


class LoanListItem(BaseModel):
    id: str
    loan_id: str | None
    borrower_id: str | None
    payment_status: str | None
    current_balance: float | None
    status: str
    source_file_id: str
    normalization_status: str
    issue_fields: list[str] = []


class LoanDetail(BaseModel):
    id: str
    source_file_id: str
    raw_record_id: str
    status: str
    loan_id: str | None
    borrower_id: str | None
    loan_type: str | None
    origination_date: date | None
    maturity_date: date | None
    original_principal: float | None
    current_balance: float | None
    interest_rate: float | None
    term_months: int | None
    borrower_state: str | None
    loan_purpose: str | None
    credit_grade: str | None
    employment_length: int | None
    income_band: str | None
    payment_status: str | None
    days_past_due: int | None
    servicer_name: str | None
    last_payment_date: date | None
    last_updated_at: date | None
    document_status: str | None
    source_system: str | None
    normalization_status: str
    normalization_notes: list[dict[str, Any]] | None = None
    field_provenance: list[dict[str, Any]] | None = None
    provenance: dict[str, Any]


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    actor_role: str | None
    actor_id: str | None
    loan_id: str | None
    entity_type: str
    entity_id: str | None
    payload: dict[str, Any] | None
    occurred_at: datetime


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int
