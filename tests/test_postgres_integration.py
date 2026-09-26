"""Integration tests against an isolated, migrated PostgreSQL database."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
import os
import sys
from threading import Event
from typing import Any
from uuid import UUID

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app import targets as targets_module
from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import CheckResult
from app.monitoring import MonitorOutcome


pytestmark = pytest.mark.integration


def run_async(awaitable: Any) -> Any:
    """Run database setup safely with Psycopg on Windows."""
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(awaitable)


@pytest.fixture(scope="session")
def postgres_test_url() -> Iterator[str]:
    """Apply migrations only to an explicitly test-named database."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")

    database_name = make_url(database_url).database or ""
    if "test" not in database_name.lower():
        raise RuntimeError("TEST_DATABASE_URL must reference a test-named database")

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        get_settings.cache_clear()
    yield database_url


@pytest.fixture
def postgres_api(
    postgres_test_url: str,
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    """Provide an API client backed by a clean real PostgreSQL database."""
    test_engine = create_async_engine(postgres_test_url, poolclass=NullPool)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def clear_database() -> None:
        async with test_engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE TABLE alerts, incidents, check_results, targets "
                    "RESTART IDENTITY CASCADE"
                )
            )

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    run_async(clear_database())
    app.dependency_overrides[get_session] = override_session
    try:
        backend_options = (
            {"loop_factory": asyncio.SelectorEventLoop}
            if sys.platform == "win32"
            else None
        )
        with TestClient(app, backend_options=backend_options) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        run_async(clear_database())
        run_async(test_engine.dispose())


def create_target(
    client: TestClient,
    name: str,
    url: str,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    response = client.post(
        "/targets",
        json={"name": name, "url": url, "enabled": enabled},
    )
    assert response.status_code == 201
    return response.json()


def healthy_outcome(response_time_ms: int = 42) -> MonitorOutcome:
    return MonitorOutcome(
        status="Healthy",
        http_status_code=200,
        response_time_ms=response_time_ms,
        error_message=None,
        tls_expires_at=None,
        security_score=100,
        security_findings={"missing": []},
    )


def test_latest_check_is_consistent_and_deterministic(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = postgres_api
    target = create_target(client, "Target", "https://example.com")
    target_id = UUID(target["id"])
    checked_at = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    async def insert_checks() -> tuple[int, int]:
        async with session_factory() as session:
            first = CheckResult(
                target_id=target_id,
                checked_at=checked_at,
                **asdict(healthy_outcome(40)),
            )
            second = CheckResult(
                target_id=target_id,
                checked_at=checked_at,
                **asdict(healthy_outcome(80)),
            )
            session.add_all([first, second])
            await session.commit()
            return first.id, second.id

    first_id, second_id = run_async(insert_checks())
    assert second_id > first_id

    listed = client.get("/targets").json()["items"][0]
    read = client.get(f"/targets/{target['id']}").json()
    updated = client.patch(
        f"/targets/{target['id']}",
        json={"name": "Updated"},
    ).json()

    for response_target in (listed, read, updated):
        assert response_target["latest_check"]["id"] == second_id
        assert response_target["latest_check"]["response_time_ms"] == 80


def test_pagination_and_database_uniqueness(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = postgres_api
    create_target(client, "First", "https://first.example.com")
    second = create_target(client, "Second", "https://second.example.com")
    create_target(client, "Third", "https://third.example.com")

    page = client.get("/targets?limit=1&offset=1")

    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert page.json()["items"][0]["id"] == second["id"]

    duplicate = client.post(
        "/targets",
        json={"name": "Duplicate", "url": "https://SECOND.example.com:443"},
    )
    assert duplicate.status_code == 409


def test_delete_cascades_check_history(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = postgres_api
    target = create_target(client, "Target", "https://example.com")

    async def successful_check(_: str) -> MonitorOutcome:
        return healthy_outcome()

    monkeypatch.setattr(targets_module, "monitor_url", successful_check)
    assert client.post(f"/targets/{target['id']}/checks").status_code == 201
    assert client.delete(f"/targets/{target['id']}").status_code == 204

    async def result_count() -> int:
        async with session_factory() as session:
            return await session.scalar(select(func.count()).select_from(CheckResult)) or 0

    assert run_async(result_count()) == 0


def test_disabled_target_can_be_checked_manually(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = postgres_api
    target = create_target(
        client,
        "Disabled",
        "https://example.com",
        enabled=False,
    )

    async def successful_check(_: str) -> MonitorOutcome:
        return healthy_outcome()

    monkeypatch.setattr(targets_module, "monitor_url", successful_check)

    response = client.post(f"/targets/{target['id']}/checks")

    assert response.status_code == 201
    assert response.json()["status"] == "Healthy"


def test_deletion_during_check_returns_conflict(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = postgres_api
    target = create_target(client, "Target", "https://example.com")
    started = Event()
    release = Event()

    async def delayed_check(_: str) -> MonitorOutcome:
        started.set()
        released = await asyncio.to_thread(release.wait, 10)
        if not released:
            raise TimeoutError("Test did not release the delayed monitor")
        return healthy_outcome()

    monkeypatch.setattr(targets_module, "monitor_url", delayed_check)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.post,
            f"/targets/{target['id']}/checks",
        )
        assert started.wait(5)
        assert client.delete(f"/targets/{target['id']}").status_code == 204
        release.set()
        response = future.result(timeout=10)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Target was deleted while the check was running"
    }


def test_latest_check_index_exists(
    postgres_api: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    _, session_factory = postgres_api

    async def index_definition() -> str | None:
        async with session_factory() as session:
            return await session.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND indexname = 'ix_check_results_target_latest'"
                )
            )

    definition = run_async(index_definition())
    assert definition is not None
    assert "target_id" in definition
    assert "checked_at DESC" in definition
    assert "id DESC" in definition
