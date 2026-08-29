"""servicer: servicer_records (second source for source_conflict)

Revision ID: 0008_servicer
Revises: 0007_verified
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_servicer"
down_revision: str | None = "0007_verified"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "servicer_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("raw_record_id", sa.String(), sa.ForeignKey("raw_records.id"), nullable=False),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("current_balance", sa.Numeric(18, 2), nullable=True),
        sa.Column("payment_status", sa.String(), nullable=True),
        sa.Column("days_past_due", sa.Integer(), nullable=True),
        sa.Column("last_updated_at", sa.Date(), nullable=True),
        sa.Column("servicer_name", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_servicer_records_source_file_id", "servicer_records", ["source_file_id"])
    op.create_index("ix_servicer_records_loan_id", "servicer_records", ["loan_id"])


def downgrade() -> None:
    op.drop_table("servicer_records")
