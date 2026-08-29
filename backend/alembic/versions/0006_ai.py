"""ai: ai_audit_logs, ai_recommendations

Revision ID: 0006_ai
Revises: 0005_review
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_ai"
down_revision: str | None = "0005_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("context_hash", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_audit_logs_kind", "ai_audit_logs", ["kind"])

    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("loan_pk", sa.String(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("exception_id", sa.String(), sa.ForeignKey("exceptions.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("suggested_field", sa.String(), nullable=True),
        sa.Column("suggested_value", sa.String(), nullable=True),
        sa.Column("ai_audit_log_id", sa.String(), sa.ForeignKey("ai_audit_logs.id"), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disposition", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_recommendations_loan_pk", "ai_recommendations", ["loan_pk"])
    op.create_index("ix_ai_recommendations_exception_id", "ai_recommendations", ["exception_id"])
    op.create_index("ix_ai_recommendations_kind", "ai_recommendations", ["kind"])


def downgrade() -> None:
    op.drop_table("ai_recommendations")
    op.drop_table("ai_audit_logs")
