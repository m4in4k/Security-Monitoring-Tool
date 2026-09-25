"""Relational models for monitored targets and their results."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""


class Target(Base):
    """An authorized web endpoint monitored by Sekuro."""

    __tablename__ = "targets"
    __table_args__ = (
        CheckConstraint(
            "check_interval_seconds BETWEEN 60 AND 86400",
            name="ck_targets_check_interval_range",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_targets_name_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    check_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=300,
        server_default="300",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    check_results: Mapped[list["CheckResult"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
    )


class CheckResult(Base):
    """The outcome of one monitoring check."""

    __tablename__ = "check_results"
    __table_args__ = (
        CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_check_results_response_time_nonnegative",
        ),
        CheckConstraint(
            "security_score IS NULL OR security_score BETWEEN 0 AND 100",
            name="ck_check_results_security_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        index=True,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20))
    http_status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    tls_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    security_score: Mapped[int | None] = mapped_column(Integer)
    security_findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    target: Mapped[Target] = relationship(back_populates="check_results")


class Incident(Base):
    """A period during which a target is degraded or unavailable."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), server_default="open")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cause: Mapped[str | None] = mapped_column(Text)

    target: Mapped[Target] = relationship(back_populates="incidents")


class Alert(Base):
    """A noteworthy monitoring event presented to the user."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        index=True,
    )
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    target: Mapped[Target] = relationship(back_populates="alerts")
