"""verified: verified_loans

Revision ID: 0007_verified
Revises: 0006_ai
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_verified"
down_revision: str | None = "0006_ai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verified_loans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("loan_pk", sa.String(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("validation_summary", sa.JSON(), nullable=True),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("ai_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_recommendation_ids", sa.JSON(), nullable=True),
        sa.Column("record_hash", sa.String(), nullable=False),
        sa.Column("supersedes_version", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("loan_pk", "version", name="uq_verified_loan_version"),
    )
    op.create_index("ix_verified_loans_loan_pk", "verified_loans", ["loan_pk"])
    op.create_index("ix_verified_loans_loan_id", "verified_loans", ["loan_id"])
    op.create_index("ix_verified_loans_record_hash", "verified_loans", ["record_hash"])


def downgrade() -> None:
    op.drop_table("verified_loans")
