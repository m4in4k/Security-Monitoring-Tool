"""Safe HTTP availability and security monitoring."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from socket import AF_INET, AF_INET6, AF_UNSPEC, SOCK_STREAM, AddressFamily
import ssl
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_REDIRECT_LIMIT = 3
DNS_TIMEOUT_SECONDS = 3.0
ALLOWED_PORTS = frozenset({80, 443})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")


class UnsafeTargetError(ValueError):
    """Raised before a request can reach a prohibited destination."""


class MonitoringError(RuntimeError):
    """Raised when a safe destination cannot be checked successfully."""


@dataclass(frozen=True, slots=True)
class Destination:
    """A parsed and resolved HTTP destination."""

    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HTTPObservation:
    """HTTP response metadata collected without downloading the body."""

    status_code: int
    headers: dict[str, str]
    final_url: str
    redirect_count: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class MonitorOutcome:
    """Data persisted for a completed or failed monitoring attempt."""

    status: str
    http_status_code: int | None
    response_time_ms: int | None
    error_message: str | None
    tls_expires_at: datetime | None
    security_score: int | None
    security_findings: dict[str, Any]


def _public_ip(value: str) -> IPv4Address | IPv6Address:
    try:
        address = ip_address(value)
    except ValueError as error:
        raise UnsafeTargetError("Target resolved to an invalid IP address") from error

    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global:
        raise UnsafeTargetError("Target resolves to a non-public IP address")
    return address


async def _get_address_info(
    hostname: str,
    port: int,
    family: AddressFamily,
) -> list[tuple[Any, ...]]:
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo(
        hostname,
        port,
        family=family,
        type=SOCK_STREAM,
    )


async def resolve_public_addresses(
    hostname: str,
    port: int,
    family: AddressFamily = AF_UNSPEC,
) -> tuple[str, ...]:
    """Resolve a host and reject the entire result if any address is unsafe."""
    try:
        literal = _public_ip(hostname)
    except UnsafeTargetError:
        try:
            ip_address(hostname)
        except ValueError:
            literal = None
        else:
            raise

    if literal is not None:
        return (str(literal),)

    try:
        records = await asyncio.wait_for(
            _get_address_info(hostname, port, family),
            timeout=DNS_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutError) as error:
        raise MonitoringError("DNS resolution failed") from error

    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        raise MonitoringError("DNS resolution returned no addresses")
    for address in addresses:
        _public_ip(address)
    return addresses


async def validate_destination(url: str) -> Destination:
    """Validate URL syntax, port policy, hostname, and all DNS results."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise UnsafeTargetError("Target URL contains an invalid port") from error

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeTargetError("Only HTTP and HTTPS targets are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeTargetError("Target URLs cannot contain credentials")
    if not parsed.hostname:
        raise UnsafeTargetError("Target URL must include a hostname")

    hostname = parsed.hostname.lower().rstrip(".")
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(BLOCKED_HOST_SUFFIXES)
        or "%" in hostname
    ):
        raise UnsafeTargetError("Target hostname is prohibited")

    resolved_port = port or (443 if scheme == "https" else 80)
    if resolved_port not in ALLOWED_PORTS:
        raise UnsafeTargetError("Only ports 80 and 443 are allowed")

    addresses = await resolve_public_addresses(hostname, resolved_port)
    return Destination(url, scheme, hostname, resolved_port, addresses)


class SafeResolver(AbstractResolver):
    """aiohttp resolver that never returns a private or reserved address."""

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: AddressFamily = AF_INET,
    ) -> list[ResolveResult]:
        addresses = await resolve_public_addresses(host, port, family)
        return [
            ResolveResult(
                hostname=host,
                host=address,
                port=port,
                family=AF_INET
                if isinstance(ip_address(address), IPv4Address)
                else AF_INET6,
                proto=0,
                flags=0,
            )
            for address in addresses
        ]

    async def close(self) -> None:
        return None


async def fetch_with_redirects(
    session: aiohttp.ClientSession,
    url: str,
    *,
    redirect_limit: int = DEFAULT_REDIRECT_LIMIT,
) -> HTTPObservation:
    """Fetch response headers while validating every redirect destination."""
    current_url = url
    started_at = perf_counter()

    for redirect_count in range(redirect_limit + 1):
        await validate_destination(current_url)
        async with session.get(current_url, allow_redirects=False) as response:
            if response.status in REDIRECT_STATUSES and "Location" in response.headers:
                if redirect_count == redirect_limit:
                    raise MonitoringError("Redirect limit exceeded")
                current_url = urljoin(current_url, response.headers["Location"])
                continue

            return HTTPObservation(
                status_code=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                final_url=current_url,
                redirect_count=redirect_count,
                latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
            )

    raise MonitoringError("Redirect limit exceeded")


async def fetch_tls_expiry(destination: Destination, timeout_seconds: float) -> datetime:
    """Perform a verified TLS handshake against a prevalidated public IP."""
    context = ssl.create_default_context()
    last_error: Exception | None = None

    for address in destination.addresses:
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=address,
                    port=destination.port,
                    ssl=context,
                    server_hostname=destination.hostname,
                ),
                timeout=timeout_seconds,
            )
            ssl_object = writer.get_extra_info("ssl_object")
            certificate = ssl_object.getpeercert() if ssl_object else None
            not_after = certificate.get("notAfter") if certificate else None
            if not isinstance(not_after, str):
                raise MonitoringError("TLS certificate has no expiry date")
            return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC)
        except (OSError, TimeoutError, ssl.SSLError, MonitoringError) as error:
            last_error = error
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

    raise MonitoringError("TLS certificate inspection failed") from last_error


def assess_security_headers(
    headers: dict[str, str],
    *,
    is_https: bool,
) -> tuple[int, dict[str, Any]]:
    """Score a small, explainable set of browser security controls."""
    content_security_policy = headers.get("content-security-policy", "")
    checks = {
        "https": is_https,
        "content_security_policy": bool(content_security_policy),
        "strict_transport_security": is_https
        and bool(headers.get("strict-transport-security")),
        "x_content_type_options": headers.get("x-content-type-options", "").lower()
        == "nosniff",
        "frame_protection": bool(headers.get("x-frame-options"))
        or "frame-ancestors" in content_security_policy.lower(),
        "referrer_policy": bool(headers.get("referrer-policy")),
        "permissions_policy": bool(headers.get("permissions-policy")),
    }
    passed = sum(checks.values())
    score = round(passed / len(checks) * 100)
    return score, {
        "checks": checks,
        "missing": [name for name, present in checks.items() if not present],
    }


def _unsafe_cause(error: BaseException) -> UnsafeTargetError | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, UnsafeTargetError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


async def monitor_url(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    redirect_limit: int = DEFAULT_REDIRECT_LIMIT,
) -> MonitorOutcome:
    """Run one bounded availability, TLS, and header-security check."""
    timeout = aiohttp.ClientTimeout(
        total=timeout_seconds,
        connect=min(5.0, timeout_seconds),
    )
    connector = aiohttp.TCPConnector(
        resolver=SafeResolver(),
        use_dns_cache=False,
        force_close=True,
        limit=4,
        ssl=ssl.create_default_context(),
    )

    try:
        await validate_destination(url)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "SekuroMonitor/0.1"},
        ) as session:
            async with asyncio.timeout(timeout_seconds):
                observation = await fetch_with_redirects(
                    session,
                    url,
                    redirect_limit=redirect_limit,
                )
    except UnsafeTargetError:
        raise
    except (aiohttp.ClientError, TimeoutError, MonitoringError) as error:
        unsafe_error = _unsafe_cause(error)
        if unsafe_error is not None:
            raise unsafe_error from error
        return MonitorOutcome(
            status="Down",
            http_status_code=None,
            response_time_ms=None,
            error_message=str(error) or error.__class__.__name__,
            tls_expires_at=None,
            security_score=None,
            security_findings={},
        )

    try:
        final_destination = await validate_destination(observation.final_url)
    except UnsafeTargetError:
        raise
    except MonitoringError as error:
        return MonitorOutcome(
            status="Down",
            http_status_code=observation.status_code,
            response_time_ms=observation.latency_ms,
            error_message=str(error),
            tls_expires_at=None,
            security_score=None,
            security_findings={"final_url": observation.final_url},
        )
    score, findings = assess_security_headers(
        observation.headers,
        is_https=final_destination.scheme == "https",
    )
    findings.update(
        {
            "final_url": observation.final_url,
            "redirect_count": observation.redirect_count,
        }
    )

    tls_expires_at: datetime | None = None
    tls_error: str | None = None
    if final_destination.scheme == "https":
        try:
            tls_expires_at = await fetch_tls_expiry(
                final_destination,
                min(5.0, timeout_seconds),
            )
        except MonitoringError as error:
            tls_error = str(error)
            findings["tls_error"] = tls_error

    if observation.status_code >= 500:
        status = "Down"
    elif observation.status_code >= 400 or tls_error:
        status = "Warning"
    else:
        status = "Healthy"

    if tls_expires_at is not None:
        days_remaining = max(0, (tls_expires_at - datetime.now(UTC)).days)
        findings["tls_days_remaining"] = days_remaining
        if days_remaining < 30 and status == "Healthy":
            status = "Warning"

    return MonitorOutcome(
        status=status,
        http_status_code=observation.status_code,
        response_time_ms=observation.latency_ms,
        error_message=tls_error,
        tls_expires_at=tls_expires_at,
        security_score=score,
        security_findings=findings,
    )
