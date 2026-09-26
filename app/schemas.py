"""Pydantic request and response models."""

from datetime import datetime
from uuid import UUID

from typing import Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


http_url_adapter = TypeAdapter(AnyHttpUrl)


def normalize_http_url(value: str) -> str:
    """Validate and normalize an HTTP or HTTPS URL."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("URL cannot be empty")
    parsed = http_url_adapter.validate_python(candidate)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL cannot contain credentials")
    if parsed.port not in {80, 443}:
        raise ValueError("URL must use port 80 or 443")
    if parsed.fragment is not None:
        raise ValueError("URL cannot contain a fragment")
    return str(parsed)


class TargetCreate(BaseModel):
    """Fields accepted when creating a monitored target."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    url: str
    enabled: bool = True
    check_interval_seconds: int = Field(default=300, ge=60, le=86_400)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_http_url(value)


class TargetUpdate(BaseModel):
    """Fields accepted when updating a monitored target."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = None
    enabled: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=60, le=86_400)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return normalize_http_url(value) if value is not None else None

    @model_validator(mode="after")
    def reject_empty_or_null_update(self) -> Self:
        updates = self.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("At least one field must be supplied")
        if any(value is None for value in updates.values()):
            raise ValueError("Updated fields cannot be null")
        return self


class CheckResultRead(BaseModel):
    """Public representation of one monitoring attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: UUID
    checked_at: datetime
    status: str
    http_status_code: int | None
    response_time_ms: int | None
    error_message: str | None
    tls_expires_at: datetime | None
    security_score: int | None
    security_findings: dict[str, object] | None


class UserRead(BaseModel):
    """Public representation of the authenticated Sekuro user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    display_name: str | None
    created_at: datetime
    updated_at: datetime


class TargetRead(BaseModel):
    """Public representation of a monitored target."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    enabled: bool
    check_interval_seconds: int
    created_at: datetime
    updated_at: datetime
    latest_check: CheckResultRead | None = None


class TargetPage(BaseModel):
    """One page of monitored targets and pagination metadata."""

    items: list[TargetRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
