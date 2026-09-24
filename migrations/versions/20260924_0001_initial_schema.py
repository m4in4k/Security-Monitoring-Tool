"""Create monitoring tables.

Revision ID: 20260924_0001
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260924_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "check_interval_seconds",
            sa.Integer(),
            server_default="300",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "check_interval_seconds BETWEEN 60 AND 86400",
            name="ck_targets_check_interval_range",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_targets_name_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_targets_url", "targets", ["url"], unique=True)

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_target_id", "alerts", ["target_id"])

    op.create_table(
        "check_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tls_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("security_score", sa.Integer(), nullable=True),
        sa.Column("security_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_check_results_response_time_nonnegative",
        ),
        sa.CheckConstraint(
            "security_score IS NULL OR security_score BETWEEN 0 AND 100",
            name="ck_check_results_security_score_range",
        ),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_results_checked_at", "check_results", ["checked_at"])
    op.create_index("ix_check_results_target_id", "check_results", ["target_id"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_target_id", "incidents", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_incidents_target_id", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_check_results_target_id", table_name="check_results")
    op.drop_index("ix_check_results_checked_at", table_name="check_results")
    op.drop_table("check_results")
    op.drop_index("ix_alerts_target_id", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_targets_url", table_name="targets")
    op.drop_table("targets")
