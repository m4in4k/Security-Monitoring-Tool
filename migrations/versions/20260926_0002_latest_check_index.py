"""Index newest checks per target.

Revision ID: 20260926_0002
Revises: 20260924_0001
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0002"
down_revision: str | None = "20260924_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_check_results_target_latest",
        "check_results",
        ["target_id", sa.text("checked_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_check_results_target_latest", table_name="check_results")
