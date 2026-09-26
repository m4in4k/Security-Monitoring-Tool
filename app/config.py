"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
from functools import lru_cache
from os import getenv

from dotenv import load_dotenv


load_dotenv()


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://sekuro:sekuro@localhost:5432/sekuro"
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the API process."""

    database_url: str
    auth_issuer: str
    auth_audience: str
    auth_jwks_url: str
    auth_algorithms: tuple[str, ...]
    auth_authorized_parties: tuple[str, ...]
    cors_origins: tuple[str, ...]
    history_retention_days: int = 90
    scheduler_poll_seconds: float = 5.0
    scheduler_max_concurrency: int = 10
    scheduler_batch_size: int = 10
    scheduler_claim_ttl_seconds: float = 300.0
    scheduler_max_attempts: int = 3
    scheduler_retry_base_seconds: float = 1.0
    scheduler_retry_max_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    """Return cached settings after reading the process environment."""
    issuer = getenv("AUTH_ISSUER", "").rstrip("/")
    algorithms = tuple(
        algorithm.strip()
        for algorithm in getenv("AUTH_ALGORITHMS", "RS256").split(",")
        if algorithm.strip()
    )
    jwks_url = getenv("AUTH_JWKS_URL", "").strip()
    authorized_parties = tuple(
        party.strip().rstrip("/")
        for party in getenv(
            "AUTH_AUTHORIZED_PARTIES",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if party.strip()
    )
    cors_origins = tuple(
        origin.strip().rstrip("/")
        for origin in getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
    history_retention_days = int(getenv("HISTORY_RETENTION_DAYS", "90"))
    if history_retention_days < 1:
        raise ValueError("HISTORY_RETENTION_DAYS must be at least 1")
    scheduler_poll_seconds = float(getenv("SCHEDULER_POLL_SECONDS", "5"))
    scheduler_max_concurrency = int(getenv("SCHEDULER_MAX_CONCURRENCY", "10"))
    scheduler_batch_size = int(getenv("SCHEDULER_BATCH_SIZE", "10"))
    scheduler_claim_ttl_seconds = float(
        getenv("SCHEDULER_CLAIM_TTL_SECONDS", "300")
    )
    scheduler_max_attempts = int(getenv("SCHEDULER_MAX_ATTEMPTS", "3"))
    scheduler_retry_base_seconds = float(
        getenv("SCHEDULER_RETRY_BASE_SECONDS", "1")
    )
    scheduler_retry_max_seconds = float(
        getenv("SCHEDULER_RETRY_MAX_SECONDS", "30")
    )
    positive_settings = {
        "SCHEDULER_POLL_SECONDS": scheduler_poll_seconds,
        "SCHEDULER_MAX_CONCURRENCY": scheduler_max_concurrency,
        "SCHEDULER_BATCH_SIZE": scheduler_batch_size,
        "SCHEDULER_CLAIM_TTL_SECONDS": scheduler_claim_ttl_seconds,
        "SCHEDULER_MAX_ATTEMPTS": scheduler_max_attempts,
        "SCHEDULER_RETRY_BASE_SECONDS": scheduler_retry_base_seconds,
        "SCHEDULER_RETRY_MAX_SECONDS": scheduler_retry_max_seconds,
    }
    for name, value in positive_settings.items():
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")
    return Settings(
        database_url=getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        auth_issuer=issuer,
        auth_audience=getenv("AUTH_AUDIENCE", ""),
        auth_jwks_url=jwks_url or (
            f"{issuer}/.well-known/jwks.json" if issuer else ""
        ),
        auth_algorithms=algorithms,
        auth_authorized_parties=authorized_parties,
        cors_origins=cors_origins,
        history_retention_days=history_retention_days,
        scheduler_poll_seconds=scheduler_poll_seconds,
        scheduler_max_concurrency=scheduler_max_concurrency,
        scheduler_batch_size=scheduler_batch_size,
        scheduler_claim_ttl_seconds=scheduler_claim_ttl_seconds,
        scheduler_max_attempts=scheduler_max_attempts,
        scheduler_retry_base_seconds=scheduler_retry_base_seconds,
        scheduler_retry_max_seconds=scheduler_retry_max_seconds,
    )
