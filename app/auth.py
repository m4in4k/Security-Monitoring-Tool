"""OIDC bearer-token validation and local user provisioning."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.models import User


bearer_scheme = HTTPBearer(auto_error=False)
Session = Annotated[AsyncSession, Depends(get_session)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@dataclass(frozen=True, slots=True)
class IdentityClaims:
    """Validated identity values used to provision a local user."""

    issuer: str
    subject: str
    email: str | None
    display_name: str | None


def unauthorized(detail: str = "Invalid or expired access token") -> HTTPException:
    """Return the consistent bearer authentication error."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_auth_settings(settings: Settings) -> None:
    """Fail closed when protected routes lack identity-provider configuration."""
    if not (
        settings.auth_issuer
        and settings.auth_audience
        and settings.auth_jwks_url
        and settings.auth_algorithms
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )


@lru_cache(maxsize=8)
def jwks_client(jwks_url: str) -> PyJWKClient:
    """Reuse the provider key cache between requests."""
    return PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)


def decode_access_token(token: str, settings: Settings) -> IdentityClaims:
    """Verify a provider JWT and return only trusted identity claims."""
    require_auth_settings(settings)
    try:
        signing_key = jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token)
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(settings.auth_algorithms),
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            leeway=5,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except (PyJWTError, ValueError) as error:
        raise unauthorized() from error

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise unauthorized()
    authorized_party = payload.get("azp")
    if settings.auth_authorized_parties and (
        not isinstance(authorized_party, str)
        or authorized_party.rstrip("/") not in settings.auth_authorized_parties
    ):
        raise unauthorized()
    email = payload.get("email")
    display_name = payload.get("name") or payload.get("display_name")
    return IdentityClaims(
        issuer=settings.auth_issuer,
        subject=subject,
        email=email if isinstance(email, str) else None,
        display_name=display_name if isinstance(display_name, str) else None,
    )


async def get_current_user(credentials: Credentials, session: Session) -> User:
    """Authenticate the request and resolve or provision its local user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("Authentication required")

    settings = get_settings()
    claims = await asyncio.to_thread(
        decode_access_token,
        credentials.credentials,
        settings,
    )
    user = await session.scalar(
        select(User).where(
            User.issuer == claims.issuer,
            User.subject == claims.subject,
        )
    )
    if user is None:
        user = User(
            issuer=claims.issuer,
            subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            user = await session.scalar(
                select(User).where(
                    User.issuer == claims.issuer,
                    User.subject == claims.subject,
                )
            )
            if user is None:
                raise
        else:
            await session.refresh(user)
    elif user.email != claims.email or user.display_name != claims.display_name:
        user.email = claims.email
        user.display_name = claims.display_name
        await session.commit()
        await session.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
