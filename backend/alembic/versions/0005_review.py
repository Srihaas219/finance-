"""review: review_decisions

Revision ID: 0005_review
Revises: 0004_validation
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_review"
down_revision: str | None = "0004_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("loan_pk", sa.String(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("exception_id", sa.String(), sa.ForeignKey("exceptions.id"), nullable=True),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=True),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("ai_recommendation_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_review_decisions_loan_pk", "review_decisions", ["loan_pk"])
    op.create_index("ix_review_decisions_reviewer_id", "review_decisions", ["reviewer_id"])
    op.create_index("ix_review_decisions_action", "review_decisions", ["action"])


def downgrade() -> None:
    op.drop_table("review_decisions")
