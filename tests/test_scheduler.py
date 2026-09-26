"""Deterministic tests for scheduled-check coordination and retries."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.config import Settings
from app.monitoring import MonitorOutcome, UnsafeTargetError
from app import scheduler
from app.scheduler import ClaimedTarget


def scheduler_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://test:test@localhost/test",
        "auth_issuer": "",
        "auth_audience": "",
        "auth_jwks_url": "",
        "auth_algorithms": ("RS256",),
        "auth_authorized_parties": (),
        "cors_origins": (),
        "scheduler_poll_seconds": 5.0,
        "scheduler_max_concurrency": 2,
        "scheduler_batch_size": 10,
        "scheduler_claim_ttl_seconds": 300.0,
        "scheduler_max_attempts": 3,
        "scheduler_retry_base_seconds": 1.5,
        "scheduler_retry_max_seconds": 2.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def outcome(status: str) -> MonitorOutcome:
    return MonitorOutcome(
        status=status,
        http_status_code=200 if status != "Down" else None,
        response_time_ms=20 if status != "Down" else None,
        error_message=None if status != "Down" else "temporary failure",
        tls_expires_at=None,
        security_score=100 if status != "Down" else None,
        security_findings={},
    )


def test_next_check_time_uses_controlled_aware_time() -> None:
    now = datetime(2026, 9, 27, 10, 30, tzinfo=UTC)

    assert scheduler.next_check_time(now, 300) == now + timedelta(minutes=5)


def test_due_query_filters_enabled_due_targets_and_locks_without_waiting() -> None:
    now = datetime(2026, 9, 27, 10, 30, tzinfo=UTC)
    sql = str(
        scheduler.due_targets_statement(now, 25).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "targets.enabled IS true" in sql
    assert "targets.next_check_at <=" in sql
    assert "targets.scheduler_claimed_until IS NULL" in sql
    assert "ORDER BY targets.next_check_at ASC, targets.id ASC" in sql
    assert "LIMIT 25" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_monitor_retries_down_outcomes_with_bounded_exponential_backoff() -> None:
    attempts = iter([outcome("Down"), outcome("Down"), outcome("Healthy")])
    delays: list[float] = []

    async def monitor(_: str) -> MonitorOutcome:
        return next(attempts)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = asyncio.run(
        scheduler.monitor_with_retries(
            "https://example.com/",
            settings=scheduler_settings(),
            monitor=monitor,
            sleep=sleep,
        )
    )

    assert result.status == "Healthy"
    assert delays == [1.5, 2.0]


def test_monitor_does_not_retry_an_unsafe_destination() -> None:
    attempts = 0
    delays: list[float] = []

    async def monitor(_: str) -> MonitorOutcome:
        nonlocal attempts
        attempts += 1
        raise UnsafeTargetError("Target resolves to a non-public IP address")

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = asyncio.run(
        scheduler.monitor_with_retries(
            "https://example.com/",
            settings=scheduler_settings(),
            monitor=monitor,
            sleep=sleep,
        )
    )

    assert result.status == "Down"
    assert "non-public" in (result.error_message or "")
    assert attempts == 1
    assert delays == []


def test_scheduler_limits_concurrent_claim_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = [
        ClaimedTarget(uuid4(), f"https://{index}.example.com/", 300, uuid4())
        for index in range(6)
    ]
    active = 0
    maximum_active = 0

    async def claim_due_targets(*_: object, **__: object) -> list[ClaimedTarget]:
        return claims

    async def execute_claim(*_: object, **__: object) -> bool:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        return True

    monkeypatch.setattr(scheduler, "claim_due_targets", claim_due_targets)
    monkeypatch.setattr(scheduler, "execute_claim", execute_claim)

    completed = asyncio.run(
        scheduler.run_scheduler_once(
            session_factory=object(),  # type: ignore[arg-type]
            settings=scheduler_settings(scheduler_max_concurrency=2),
            clock=lambda: datetime(2026, 9, 27, 10, 30, tzinfo=UTC),
        )
    )

    assert completed == len(claims)
    assert maximum_active == 2
