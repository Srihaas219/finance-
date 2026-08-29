"""validation: validation_runs, validation_results, exceptions

Revision ID: 0004_validation
Revises: 0003_provenance
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_validation"
down_revision: str | None = "0003_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("source_files.id"), nullable=True),
        sa.Column("ruleset_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("loans_evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("totals", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_validation_runs_source_file_id", "validation_runs", ["source_file_id"])

    op.create_table(
        "validation_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("validation_run_id", sa.String(), sa.ForeignKey("validation_runs.id"), nullable=False),
        sa.Column("loan_pk", sa.String(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=True),
        sa.Column("observed_value", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
    )
    op.create_index("ix_validation_results_run", "validation_results", ["validation_run_id"])
    op.create_index("ix_validation_results_loan_pk", "validation_results", ["loan_pk"])
    op.create_index("ix_validation_results_loan_id", "validation_results", ["loan_id"])
    op.create_index("ix_validation_results_rule_id", "validation_results", ["rule_id"])

    op.create_table(
        "exceptions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("loan_pk", sa.String(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("loan_id", sa.String(), nullable=True),
        sa.Column("borrower_id", sa.String(), nullable=True),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("exception_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("field", sa.String(), nullable=True),
        sa.Column("observed_value", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("validation_run_id", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.UniqueConstraint("loan_pk", "rule_id", "field", name="uq_exception_loan_rule_field"),
    )
    op.create_index("ix_exceptions_loan_pk", "exceptions", ["loan_pk"])
    op.create_index("ix_exceptions_loan_id", "exceptions", ["loan_id"])
    op.create_index("ix_exceptions_borrower_id", "exceptions", ["borrower_id"])
    op.create_index("ix_exceptions_rule_id", "exceptions", ["rule_id"])
    op.create_index("ix_exceptions_exception_type", "exceptions", ["exception_type"])
    op.create_index("ix_exceptions_severity", "exceptions", ["severity"])
    op.create_index("ix_exceptions_status", "exceptions", ["status"])


def downgrade() -> None:
    op.drop_table("exceptions")
    op.drop_table("validation_results")
    op.drop_table("validation_runs")
