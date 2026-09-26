"""Add OIDC users and per-user target ownership.

Revision ID: 20260926_0003
Revises: 20260926_0002
Create Date: 2026-09-26
"""

from collections.abc import Sequence
from uuid import UUID

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0003"
down_revision: str | None = "20260926_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_OWNER_ID = UUID("00000000-0000-4000-8000-000000000003")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("issuer", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("display_name", sa.String()),
    )
    op.bulk_insert(
        users,
        [
            {
                "id": LEGACY_OWNER_ID,
                "issuer": "sekuro:migration",
                "subject": "legacy-phase-2-owner",
                "display_name": "Legacy Phase 2 Owner",
            }
        ],
    )

    op.add_column("targets", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text("UPDATE targets SET owner_id = :owner_id").bindparams(
            owner_id=LEGACY_OWNER_ID
        )
    )
    op.alter_column("targets", "owner_id", nullable=False)
    op.create_foreign_key(
        "fk_targets_owner_id_users",
        "targets",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_targets_url", table_name="targets")
    op.create_index("ix_targets_owner_id", "targets", ["owner_id"])
    op.create_index(
        "ix_targets_owner_created",
        "targets",
        ["owner_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_unique_constraint(
        "uq_targets_owner_url",
        "targets",
        ["owner_id", "url"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_url = connection.execute(
        sa.text(
            "SELECT url FROM targets GROUP BY url HAVING count(*) > 1 LIMIT 1"
        )
    ).scalar_one_or_none()
    if duplicate_url is not None:
        raise RuntimeError(
            "Cannot downgrade while different users have the same target URL"
        )

    op.drop_constraint("uq_targets_owner_url", "targets", type_="unique")
    op.drop_index("ix_targets_owner_created", table_name="targets")
    op.drop_index("ix_targets_owner_id", table_name="targets")
    op.create_index("ix_targets_url", "targets", ["url"], unique=True)
    op.drop_constraint("fk_targets_owner_id_users", "targets", type_="foreignkey")
    op.drop_column("targets", "owner_id")
    op.drop_table("users")
