"""Tests for monitored-target request validation."""

import pytest
from pydantic import ValidationError

from app.schemas import TargetCreate, TargetUpdate


def test_target_create_normalizes_values() -> None:
    target = TargetCreate(name="  Portfolio  ", url="https://example.com")

    assert target.name == "Portfolio"
    assert target.url == "https://example.com/"
    assert target.enabled is True
    assert target.check_interval_seconds == 300


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),
        ("url", "ftp://example.com"),
        ("url", "https://user:password@example.com"),
        ("url", "https://example.com:8443"),
        ("url", "https://example.com/#overview"),
        ("check_interval_seconds", 59),
        ("check_interval_seconds", 86_401),
    ],
)
def test_target_create_rejects_invalid_values(field: str, value: object) -> None:
    payload = {"name": "Portfolio", "url": "https://example.com", field: value}

    with pytest.raises(ValidationError):
        TargetCreate(**payload)  # type: ignore[arg-type]


def test_target_update_only_contains_supplied_fields() -> None:
    update = TargetUpdate(enabled=False)

    assert update.model_dump(exclude_unset=True) == {"enabled": False}


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"enabled": None}])
def test_target_update_rejects_empty_or_null_updates(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TargetUpdate(**payload)  # type: ignore[arg-type]
