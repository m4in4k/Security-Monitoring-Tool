"""Request-level tests for the monitored-target API."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import targets as targets_module
from app.auth import get_current_user
from app.database import get_session
from app.main import app
from app.models import CheckResult, Target, User
from app.monitoring import MonitorOutcome, UnsafeTargetError


class FakeScalarResult:
    """Small iterable matching the part of ScalarResult used by the route."""

    def __init__(self, targets: list[Target]) -> None:
        self.targets = targets

    def __iter__(self) -> Iterator[Target]:
        return iter(self.targets)


class FakeRowResult:
    """Small row result matching the APIs used by the optimized query."""

    def __init__(self, rows: list[tuple[Target, CheckResult | None]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[Target, CheckResult | None]]:
        return self.rows

    def one_or_none(self) -> tuple[Target, CheckResult | None] | None:
        if not self.rows:
            return None
        if len(self.rows) > 1:
            raise AssertionError("Expected at most one row")
        return self.rows[0]


class FakeSession:
    """In-memory AsyncSession substitute for request behavior tests."""

    def __init__(self) -> None:
        self.targets: dict[UUID, Target] = {}
        self.pending: list[Target] = []
        self.check_results: list[CheckResult] = []

    def add(self, record: Target | CheckResult) -> None:
        if isinstance(record, CheckResult):
            record.id = len(self.check_results) + 1
            record.checked_at = datetime.now(UTC)
            self.check_results.append(record)
        else:
            self.pending.append(record)

    async def flush(self) -> None:
        candidates = [*self.targets.values(), *self.pending]
        seen_urls: dict[tuple[UUID, str], UUID | None] = {}
        for target in candidates:
            key = (target.owner_id, target.url)
            existing_id = seen_urls.get(key)
            if key in seen_urls and existing_id != target.id:
                raise IntegrityError("duplicate target URL", {}, ValueError(target.url))
            seen_urls[key] = target.id

        now = datetime.now(UTC)
        for target in self.pending:
            target.id = target.id or uuid4()
            target.created_at = target.created_at or now
            target.updated_at = target.updated_at or now
            self.targets[target.id] = target
        self.pending.clear()

    async def commit(self) -> None:
        return None

    async def refresh(self, record: Target | CheckResult) -> None:
        if isinstance(record, Target):
            record.updated_at = datetime.now(UTC)

    async def get(self, _: type[Target], target_id: UUID) -> Target | None:
        return self.targets.get(target_id)

    async def delete(self, target: Target) -> None:
        self.targets.pop(target.id, None)
        self.check_results = [
            result for result in self.check_results if result.target_id != target.id
        ]

    async def rollback(self) -> None:
        return None

    async def scalar(self, statement: Any) -> int | UUID | None:
        ids = [value for value in statement.compile().params.values() if isinstance(value, UUID)]
        description = statement.column_descriptions[0]
        if description.get("entity") is Target:
            matches = [
                target
                for target in self.targets.values()
                if target.id in ids and target.owner_id in ids
            ]
            if not matches:
                return None
            if description.get("expr") is Target:
                return matches[0]  # type: ignore[return-value]
            return matches[0].id
        if ids:
            return sum(target.owner_id in ids for target in self.targets.values())
        return len(self.targets)

    async def execute(self, statement: Any) -> FakeRowResult:
        params = statement.compile().params.values()
        ids = [value for value in params if isinstance(value, UUID)]
        target_ids = [value for value in ids if value in self.targets]
        owner_ids = [value for value in ids if value not in self.targets]
        targets = list(self.targets.values())
        if target_ids:
            targets = [target for target in targets if target.id == target_ids[0]]
        if owner_ids:
            targets = [target for target in targets if target.owner_id in owner_ids]

        targets.sort(key=lambda target: (target.created_at, target.id), reverse=True)
        offset_clause = getattr(statement, "_offset_clause", None)
        limit_clause = getattr(statement, "_limit_clause", None)
        offset = int(offset_clause.value) if offset_clause is not None else 0
        limit = int(limit_clause.value) if limit_clause is not None else len(targets)
        targets = targets[offset : offset + limit]

        rows: list[tuple[Target, CheckResult | None]] = []
        for target in targets:
            checks = [
                result
                for result in self.check_results
                if result.target_id == target.id
            ]
            latest = max(
                checks,
                key=lambda result: (result.checked_at, result.id),
                default=None,
            )
            rows.append((target, latest))
        return FakeRowResult(rows)

    async def scalars(self, statement: Any) -> FakeScalarResult:
        entity = statement.column_descriptions[0].get("entity")
        if entity is CheckResult:
            results = sorted(
                self.check_results,
                key=lambda result: (str(result.target_id), result.checked_at),
                reverse=True,
            )
            return FakeScalarResult(results)  # type: ignore[arg-type]

        targets = sorted(
            self.targets.values(),
            key=lambda target: target.created_at,
            reverse=True,
        )
        return FakeScalarResult(targets)


@pytest.fixture
def api() -> Iterator[tuple[TestClient, FakeSession]]:
    session = FakeSession()
    now = datetime.now(UTC)
    current_user = User(
        id=uuid4(),
        issuer="https://issuer.example",
        subject="alice",
        email="alice@example.com",
        display_name="Alice",
        created_at=now,
        updated_at=now,
    )

    async def override_session() -> AsyncIterator[FakeSession]:
        yield session

    async def override_current_user() -> User:
        return current_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.clear()


def create_target(client: TestClient, name: str, url: str) -> dict[str, Any]:
    response = client.post("/targets", json={"name": name, "url": url})
    assert response.status_code == 201
    return response.json()


def test_target_crud_lifecycle(api: tuple[TestClient, FakeSession]) -> None:
    client, _ = api

    assert client.get("/targets").json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }

    created = create_target(client, "  Portfolio  ", "https://example.com")
    target_id = created["id"]
    assert created["name"] == "Portfolio"
    assert created["url"] == "https://example.com/"
    assert created["enabled"] is True

    read_response = client.get(f"/targets/{target_id}")
    assert read_response.status_code == 200
    assert read_response.json() == created

    update_response = client.patch(
        f"/targets/{target_id}",
        json={"name": "Production", "enabled": False, "check_interval_seconds": 600},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Production"
    assert update_response.json()["enabled"] is False
    assert update_response.json()["check_interval_seconds"] == 600

    list_response = client.get("/targets")
    assert list_response.status_code == 200
    assert [target["id"] for target in list_response.json()["items"]] == [target_id]
    assert list_response.json()["total"] == 1

    delete_response = client.delete(f"/targets/{target_id}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert client.get(f"/targets/{target_id}").status_code == 404


def test_create_rejects_duplicate_url(api: tuple[TestClient, FakeSession]) -> None:
    client, _ = api
    create_target(client, "First", "https://EXAMPLE.com:443")

    response = client.post(
        "/targets",
        json={"name": "Duplicate", "url": "https://example.com/"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Target URL already exists"}


def test_update_rejects_duplicate_url(api: tuple[TestClient, FakeSession]) -> None:
    client, _ = api
    first = create_target(client, "First", "https://one.example.com")
    second = create_target(client, "Second", "https://two.example.com")

    response = client.patch(
        f"/targets/{second['id']}",
        json={"url": first["url"]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Target URL already exists"}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "url": "https://example.com"},
        {"name": "Target", "url": "ftp://example.com"},
        {"name": "Target", "url": "https://example.com", "check_interval_seconds": 59},
        {"name": "Target", "url": "https://example.com", "unexpected": True},
    ],
)
def test_create_rejects_invalid_payload(
    api: tuple[TestClient, FakeSession],
    payload: dict[str, object],
) -> None:
    client, _ = api

    assert client.post("/targets", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"enabled": None}])
def test_update_rejects_invalid_payload(
    api: tuple[TestClient, FakeSession],
    payload: dict[str, object],
) -> None:
    client, _ = api
    target = create_target(client, "Target", "https://example.com")

    assert client.patch(f"/targets/{target['id']}", json=payload).status_code == 422


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_missing_target_returns_404(
    api: tuple[TestClient, FakeSession],
    method: str,
) -> None:
    client, _ = api
    request = getattr(client, method)
    kwargs = {"json": {"name": "Updated"}} if method == "patch" else {}

    response = request(f"/targets/{uuid4()}", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Target not found"}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_malformed_target_id_returns_422(
    api: tuple[TestClient, FakeSession],
    method: str,
) -> None:
    client, _ = api
    request = getattr(client, method)
    kwargs = {"json": {"name": "Updated"}} if method == "patch" else {}

    assert request("/targets/not-a-uuid", **kwargs).status_code == 422


def test_manual_check_persists_monitoring_result(
    api: tuple[TestClient, FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    target = create_target(client, "Target", "https://example.com")

    async def successful_check(_: str) -> MonitorOutcome:
        return MonitorOutcome(
            status="Healthy",
            http_status_code=200,
            response_time_ms=87,
            error_message=None,
            tls_expires_at=datetime(2027, 1, 1, tzinfo=UTC),
            security_score=86,
            security_findings={"missing": ["permissions_policy"]},
        )

    monkeypatch.setattr(targets_module, "monitor_url", successful_check)

    response = client.post(f"/targets/{target['id']}/checks")

    assert response.status_code == 201
    assert response.json()["status"] == "Healthy"
    assert response.json()["response_time_ms"] == 87
    assert response.json()["security_score"] == 86
    assert len(session.check_results) == 1

    targets_response = client.get("/targets")
    assert targets_response.status_code == 200
    latest_from_list = targets_response.json()["items"][0]["latest_check"]
    assert latest_from_list["response_time_ms"] == 87

    read_response = client.get(f"/targets/{target['id']}")
    assert read_response.json()["latest_check"]["response_time_ms"] == 87

    update_response = client.patch(
        f"/targets/{target['id']}",
        json={"name": "Updated target"},
    )
    assert update_response.json()["latest_check"]["response_time_ms"] == 87


def test_manual_check_rejects_unsafe_target(
    api: tuple[TestClient, FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    target = create_target(client, "Target", "https://example.com")

    async def unsafe_check(_: str) -> MonitorOutcome:
        raise UnsafeTargetError("Target resolves to a non-public IP address")

    monkeypatch.setattr(targets_module, "monitor_url", unsafe_check)

    response = client.post(f"/targets/{target['id']}/checks")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Target resolves to a non-public IP address"
    }
    assert session.check_results == []


def test_target_list_is_paginated(api: tuple[TestClient, FakeSession]) -> None:
    client, _ = api
    first = create_target(client, "First", "https://first.example.com")
    second = create_target(client, "Second", "https://second.example.com")
    third = create_target(client, "Third", "https://third.example.com")

    response = client.get("/targets?limit=1&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert [item["id"] for item in body["items"]] == [second["id"]]
    assert first["id"] != third["id"]


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1"],
)
def test_target_list_rejects_invalid_pagination(
    api: tuple[TestClient, FakeSession],
    query: str,
) -> None:
    client, _ = api

    assert client.get(f"/targets?{query}").status_code == 422


def test_manual_check_is_allowed_for_disabled_target(
    api: tuple[TestClient, FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = api
    response = client.post(
        "/targets",
        json={
            "name": "Disabled target",
            "url": "https://example.com",
            "enabled": False,
        },
    )
    target = response.json()

    async def successful_check(_: str) -> MonitorOutcome:
        return MonitorOutcome(
            status="Healthy",
            http_status_code=200,
            response_time_ms=25,
            error_message=None,
            tls_expires_at=None,
            security_score=100,
            security_findings={"missing": []},
        )

    monkeypatch.setattr(targets_module, "monitor_url", successful_check)

    check_response = client.post(f"/targets/{target['id']}/checks")

    assert check_response.status_code == 201
    assert check_response.json()["status"] == "Healthy"


def test_check_returns_conflict_if_target_is_deleted_while_running(
    api: tuple[TestClient, FakeSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    target = create_target(client, "Target", "https://example.com")
    target_id = UUID(target["id"])

    async def delete_during_check(_: str) -> MonitorOutcome:
        session.targets.pop(target_id)
        return MonitorOutcome(
            status="Healthy",
            http_status_code=200,
            response_time_ms=25,
            error_message=None,
            tls_expires_at=None,
            security_score=100,
            security_findings={"missing": []},
        )

    monkeypatch.setattr(targets_module, "monitor_url", delete_during_check)

    response = client.post(f"/targets/{target['id']}/checks")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Target was deleted while the check was running"
    }
    assert session.check_results == []
