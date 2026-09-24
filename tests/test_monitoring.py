"""Tests for HTTP monitoring and SSRF defenses."""

import asyncio
from datetime import UTC, datetime, timedelta
from socket import AF_INET, SOCK_STREAM
from typing import Any

import pytest

from app import monitoring
from app.monitoring import (
    Destination,
    HTTPObservation,
    MonitoringError,
    UnsafeTargetError,
)


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str, *, allow_redirects: bool) -> FakeResponse:
        assert allow_redirects is False
        self.requested_urls.append(url)
        return self.responses.pop(0)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]",
        "http://localhost",
        "http://service.internal",
        "http://user:password@example.com",
        "https://example.com:8443",
        "file:///etc/passwd",
    ],
)
def test_validate_destination_blocks_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeTargetError):
        asyncio.run(monitoring.validate_destination(url))


def test_dns_resolution_rejects_mixed_public_and_private_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def mixed_answers(*_: object) -> list[tuple[Any, ...]]:
        return [
            (AF_INET, SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (AF_INET, SOCK_STREAM, 6, "", ("10.0.0.7", 443)),
        ]

    monkeypatch.setattr(monitoring, "_get_address_info", mixed_answers)

    with pytest.raises(UnsafeTargetError):
        asyncio.run(monitoring.resolve_public_addresses("example.com", 443))


def test_dns_resolution_accepts_only_public_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def public_answers(*_: object) -> list[tuple[Any, ...]]:
        return [
            (AF_INET, SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (AF_INET, SOCK_STREAM, 6, "", ("93.184.216.35", 443)),
        ]

    monkeypatch.setattr(monitoring, "_get_address_info", public_answers)

    addresses = asyncio.run(
        monitoring.resolve_public_addresses("example.com", 443)
    )

    assert addresses == ("93.184.216.34", "93.184.216.35")


def test_redirects_are_followed_manually_and_revalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated: list[str] = []

    async def record_destination(url: str) -> Destination:
        validated.append(url)
        return Destination(url, "https", "example.com", 443, ("93.184.216.34",))

    monkeypatch.setattr(monitoring, "validate_destination", record_destination)
    session = FakeSession(
        [
            FakeResponse(302, {"Location": "/login"}),
            FakeResponse(200, {"X-Content-Type-Options": "nosniff"}),
        ]
    )

    result = asyncio.run(
        monitoring.fetch_with_redirects(session, "https://example.com")  # type: ignore[arg-type]
    )

    assert session.requested_urls == [
        "https://example.com",
        "https://example.com/login",
    ]
    assert validated == session.requested_urls
    assert result.status_code == 200
    assert result.redirect_count == 1
    assert result.headers["x-content-type-options"] == "nosniff"


def test_unsafe_redirect_is_rejected_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_internal(url: str) -> Destination:
        if "127.0.0.1" in url:
            raise UnsafeTargetError("Target resolves to a non-public IP address")
        return Destination(url, "https", "example.com", 443, ("93.184.216.34",))

    monkeypatch.setattr(monitoring, "validate_destination", reject_internal)
    session = FakeSession(
        [FakeResponse(302, {"Location": "http://127.0.0.1/admin"})]
    )

    with pytest.raises(UnsafeTargetError):
        asyncio.run(
            monitoring.fetch_with_redirects(
                session, "https://example.com"
            )  # type: ignore[arg-type]
        )

    assert session.requested_urls == ["https://example.com"]


def test_redirect_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(url: str) -> Destination:
        return Destination(url, "https", "example.com", 443, ("93.184.216.34",))

    monkeypatch.setattr(monitoring, "validate_destination", allow)
    session = FakeSession(
        [
            FakeResponse(302, {"Location": "/one"}),
            FakeResponse(302, {"Location": "/two"}),
        ]
    )

    with pytest.raises(MonitoringError, match="Redirect limit exceeded"):
        asyncio.run(
            monitoring.fetch_with_redirects(
                session,  # type: ignore[arg-type]
                "https://example.com",
                redirect_limit=1,
            )
        )


def test_security_header_score() -> None:
    score, findings = monitoring.assess_security_headers(
        {
            "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
            "strict-transport-security": "max-age=31536000",
            "x-content-type-options": "nosniff",
            "referrer-policy": "strict-origin-when-cross-origin",
            "permissions-policy": "camera=()",
        },
        is_https=True,
    )

    assert score == 100
    assert findings["missing"] == []


def test_tls_expiry_uses_pinned_ip_and_original_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeSSLObject:
        def getpeercert(self) -> dict[str, str]:
            return {"notAfter": "Jan  1 00:00:00 2030 GMT"}

    class FakeWriter:
        def get_extra_info(self, name: str) -> FakeSSLObject | None:
            return FakeSSLObject() if name == "ssl_object" else None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    async def open_connection(**kwargs: object) -> tuple[object, FakeWriter]:
        calls.append(kwargs)
        return object(), FakeWriter()

    monkeypatch.setattr(monitoring.asyncio, "open_connection", open_connection)
    destination = Destination(
        "https://example.com",
        "https",
        "example.com",
        443,
        ("93.184.216.34",),
    )

    expiry = asyncio.run(monitoring.fetch_tls_expiry(destination, 1.0))

    assert expiry == datetime(2030, 1, 1, tzinfo=UTC)
    assert calls[0]["host"] == "93.184.216.34"
    assert calls[0]["server_hostname"] == "example.com"


def test_monitor_url_records_timeout_as_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = Destination(
        "https://example.com",
        "https",
        "example.com",
        443,
        ("93.184.216.34",),
    )

    async def valid(_: str) -> Destination:
        return destination

    async def timeout(*_: object, **__: object) -> HTTPObservation:
        raise TimeoutError("request timed out")

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(monitoring, "validate_destination", valid)
    monkeypatch.setattr(monitoring, "fetch_with_redirects", timeout)
    monkeypatch.setattr(monitoring.aiohttp, "TCPConnector", lambda **_: object())
    monkeypatch.setattr(
        monitoring.aiohttp,
        "ClientSession",
        lambda **_: SessionContext(),
    )

    outcome = asyncio.run(monitoring.monitor_url("https://example.com"))

    assert outcome.status == "Down"
    assert outcome.http_status_code is None
    assert outcome.error_message == "request timed out"


def test_monitor_url_collects_status_latency_tls_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = Destination(
        "https://example.com",
        "https",
        "example.com",
        443,
        ("93.184.216.34",),
    )
    expiry = datetime.now(UTC) + timedelta(days=90)

    async def valid(_: str) -> Destination:
        return destination

    async def observation(*_: object, **__: object) -> HTTPObservation:
        return HTTPObservation(
            status_code=200,
            headers={"x-content-type-options": "nosniff"},
            final_url="https://example.com",
            redirect_count=0,
            latency_ms=123,
        )

    async def tls(*_: object, **__: object) -> datetime:
        return expiry

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(monitoring, "validate_destination", valid)
    monkeypatch.setattr(monitoring, "fetch_with_redirects", observation)
    monkeypatch.setattr(monitoring, "fetch_tls_expiry", tls)
    monkeypatch.setattr(monitoring.aiohttp, "TCPConnector", lambda **_: object())
    monkeypatch.setattr(
        monitoring.aiohttp,
        "ClientSession",
        lambda **_: SessionContext(),
    )

    outcome = asyncio.run(monitoring.monitor_url("https://example.com"))

    assert outcome.status == "Healthy"
    assert outcome.http_status_code == 200
    assert outcome.response_time_ms == 123
    assert outcome.tls_expires_at == expiry
    assert outcome.security_score == 29
    assert outcome.security_findings["redirect_count"] == 0
