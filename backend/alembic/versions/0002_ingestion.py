"""ingestion: source_files, raw_records, loans, audit_events

Revision ID: 0002_ingestion
Revises: 0001_initial
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_ingestion"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_files",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("duplicate_of", sa.String(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_files_file_hash", "source_files", ["file_hash"])

    op.create_table(
        "raw_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("row_hash", sa.String(), nullable=False),
        sa.Column("import_status", sa.String(), nullable=False, server_default="imported"),
        sa.Column("failure_reason", sa.String(), nullable=True),
    )
    op.create_index("ix_raw_records_source_file_id", "raw_records", ["source_file_id"])
    op.create_index("ix_raw_records_row_hash", "raw_records", ["row_hash"])

    op.create_table(
        "loans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("raw_record_id", sa.String(), sa.ForeignKey("raw_records.id"), nullable=False),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("borrower_id", sa.String(), nullable=True),
        sa.Column("loan_type", sa.String(), nullable=True),
        sa.Column("origination_date", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("original_principal", sa.Numeric(18, 2), nullable=True),
        sa.Column("current_balance", sa.Numeric(18, 2), nullable=True),
        sa.Column("interest_rate", sa.Numeric(9, 4), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("borrower_state", sa.String(), nullable=True),
        sa.Column("loan_purpose", sa.String(), nullable=True),
        sa.Column("credit_grade", sa.String(), nullable=True),
        sa.Column("employment_length", sa.Integer(), nullable=True),
        sa.Column("income_band", sa.String(), nullable=True),
        sa.Column("payment_status", sa.String(), nullable=True),
        sa.Column("days_past_due", sa.Integer(), nullable=True),
        sa.Column("servicer_name", sa.String(), nullable=True),
        sa.Column("last_payment_date", sa.Date(), nullable=True),
        sa.Column("last_updated_at", sa.Date(), nullable=True),
        sa.Column("document_status", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="imported"),
        sa.Column("normalization_notes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_loans_loan_id", "loans", ["loan_id"])
    op.create_index("ix_loans_borrower_id", "loans", ["borrower_id"])
    op.create_index("ix_loans_payment_status", "loans", ["payment_status"])
    op.create_index("ix_loans_status", "loans", ["status"])
    op.create_index("ix_loans_source_file_id", "loans", ["source_file_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("source_files.id"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_loan_id", "audit_events", ["loan_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("loans")
    op.drop_table("raw_records")
    op.drop_table("source_files")
