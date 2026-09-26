"""Authenticated-user endpoints."""

from fastapi import APIRouter

from app.auth import CurrentUser
from app.models import User
from app.schemas import UserRead


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: CurrentUser) -> User:
    """Return the local profile for the authenticated identity."""
    return current_user
