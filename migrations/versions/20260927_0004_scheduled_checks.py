"""Add scheduled-check state and due-target index.

Revision ID: 20260927_0004
Revises: 20260926_0003
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260927_0004"
down_revision: str | None = "20260926_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "targets",
        sa.Column(
            "next_check_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "targets",
        sa.Column("scheduler_claim_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "targets",
        sa.Column(
            "scheduler_claimed_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_targets_due",
        "targets",
        ["next_check_at", "id"],
        postgresql_where=sa.text("enabled"),
    )


def downgrade() -> None:
    op.drop_index("ix_targets_due", table_name="targets")
    op.drop_column("targets", "scheduler_claimed_until")
    op.drop_column("targets", "scheduler_claim_token")
    op.drop_column("targets", "next_check_at")
