"""provenance: loans.normalization_status + loans.field_provenance

Revision ID: 0003_provenance
Revises: 0002_ingestion
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_provenance"
down_revision: str | None = "0002_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "loans",
        sa.Column("normalization_status", sa.String(), nullable=False, server_default="clean"),
    )
    op.add_column("loans", sa.Column("field_provenance", sa.JSON(), nullable=True))
    op.create_index("ix_loans_normalization_status", "loans", ["normalization_status"])


def downgrade() -> None:
    op.drop_index("ix_loans_normalization_status", table_name="loans")
    op.drop_column("loans", "field_provenance")
    op.drop_column("loans", "normalization_status")
