"""Authentication and token-validation tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
import pytest

from app import auth
from app.config import Settings
from app.main import app


ISSUER = "https://issuer.example"
AUDIENCE = "sekuro-api"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()


def settings(*, algorithms: tuple[str, ...] = ("RS256",)) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused/unused",
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_jwks_url=f"{ISSUER}/.well-known/jwks.json",
        auth_algorithms=algorithms,
        auth_authorized_parties=("http://localhost:5173",),
        cors_origins=("http://localhost:5173",),
    )


def token(
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_delta: timedelta = timedelta(minutes=5),
    algorithm: str = "RS256",
    authorized_party: str = "http://localhost:5173",
) -> str:
    now = datetime.now(UTC)
    key: Any = PRIVATE_KEY if algorithm == "RS256" else "test-secret-at-least-32-bytes-long"
    return jwt.encode(
        {
            "iss": issuer,
            "sub": "user_alice",
            "aud": audience,
            "iat": now,
            "exp": now + expires_delta,
            "email": "alice@example.com",
            "name": "Alice",
            "azp": authorized_party,
        },
        key,
        algorithm=algorithm,
    )


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def get_signing_key_from_jwt(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(key=PUBLIC_KEY)

    monkeypatch.setattr(auth, "jwks_client", lambda _: FakeClient())


def test_valid_token_returns_trusted_identity() -> None:
    claims = auth.decode_access_token(token(), settings())

    assert claims.issuer == ISSUER
    assert claims.subject == "user_alice"
    assert claims.email == "alice@example.com"
    assert claims.display_name == "Alice"


@pytest.mark.parametrize(
    "encoded",
    [
        token(expires_delta=timedelta(minutes=-1)),
        token(issuer="https://attacker.example"),
        token(audience="another-api"),
        token(authorized_party="https://attacker.example"),
        token(algorithm="HS256"),
        "not-a-jwt",
    ],
    ids=[
        "expired",
        "wrong-issuer",
        "wrong-audience",
        "wrong-authorized-party",
        "wrong-algorithm",
        "malformed",
    ],
)
def test_invalid_tokens_are_rejected(encoded: str) -> None:
    with pytest.raises(HTTPException) as caught:
        auth.decode_access_token(encoded, settings())

    assert caught.value.status_code == 401


def test_protected_routes_require_authentication_but_health_is_public() -> None:
    with TestClient(app) as client:
        response = client.get("/targets")
        health = client.get("/health")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert health.status_code == 200
