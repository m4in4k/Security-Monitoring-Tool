"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
from functools import lru_cache
from os import getenv


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://sekuro:sekuro@localhost:5432/sekuro"
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the API process."""

    database_url: str


@lru_cache
def get_settings() -> Settings:
    """Return cached settings after reading the process environment."""
    return Settings(database_url=getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
