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
    )
