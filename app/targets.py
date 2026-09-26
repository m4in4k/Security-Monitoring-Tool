"""CRUD endpoints for monitored targets."""

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.auth import CurrentUser
from app.models import CheckResult, Target, User
from app.monitoring import UnsafeTargetError, monitor_url
from app.schemas import (
    CheckResultRead,
    TargetCreate,
    TargetPage,
    TargetRead,
    TargetUpdate,
)


router = APIRouter(prefix="/targets", tags=["targets"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def get_target_or_404(
    target_id: UUID,
    owner_id: UUID,
    session: AsyncSession,
) -> Target:
    target = await session.scalar(
        select(Target).where(Target.id == target_id, Target.owner_id == owner_id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


def target_with_latest_check_statement():
    """Select targets with only their newest persisted check result."""
    latest_check_id = (
        select(CheckResult.id)
        .where(CheckResult.target_id == Target.id)
        .order_by(CheckResult.checked_at.desc(), CheckResult.id.desc())
        .limit(1)
        .correlate(Target)
        .scalar_subquery()
    )
    return select(Target, CheckResult).outerjoin(
        CheckResult,
        CheckResult.id == latest_check_id,
    )


def target_read(target: Target, latest_check: CheckResult | None) -> TargetRead:
    """Build the public target representation with a consistent latest check."""
    check = (
        CheckResultRead.model_validate(latest_check)
        if latest_check is not None
        else None
    )
    return TargetRead.model_validate(target).model_copy(update={"latest_check": check})


async def get_target_read_or_404(
    target_id: UUID,
    owner_id: UUID,
    session: AsyncSession,
) -> TargetRead:
    row = (
        await session.execute(
            target_with_latest_check_statement().where(
                Target.id == target_id,
                Target.owner_id == owner_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target_read(row[0], row[1])


@router.get("", response_model=TargetPage)
async def list_targets(
    session: Session,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TargetPage:
    """Return one page of targets with only each target's newest check."""
    total = await session.scalar(
        select(func.count()).select_from(Target).where(
            Target.owner_id == current_user.id
        )
    )
    rows = (
        await session.execute(
            target_with_latest_check_statement()
            .where(Target.owner_id == current_user.id)
            .order_by(Target.created_at.desc(), Target.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return TargetPage(
        items=[target_read(target, latest_check) for target, latest_check in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
async def create_target(
    payload: TargetCreate,
    session: Session,
    current_user: CurrentUser,
) -> Target:
    """Create an authorized monitoring target."""
    target = Target(owner_id=current_user.id, **payload.model_dump())
    session.add(target)
    try:
        await session.flush()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Target URL already exists") from error
    await session.commit()
    await session.refresh(target)
    return target


@router.get("/{target_id}", response_model=TargetRead)
async def read_target(
    target_id: UUID,
    session: Session,
    current_user: CurrentUser,
) -> TargetRead:
    """Return one monitored target."""
    return await get_target_read_or_404(target_id, current_user.id, session)


@router.patch("/{target_id}", response_model=TargetRead)
async def update_target(
    target_id: UUID,
    payload: TargetUpdate,
    session: Session,
    current_user: CurrentUser,
) -> TargetRead:
    """Update selected fields on a monitored target."""
    target = await get_target_or_404(target_id, current_user.id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    try:
        await session.flush()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Target URL already exists") from error
    await session.commit()
    return await get_target_read_or_404(target_id, current_user.id, session)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(
    target_id: UUID,
    session: Session,
    current_user: CurrentUser,
) -> Response:
    """Delete a target and its monitoring history."""
    target = await get_target_or_404(target_id, current_user.id, session)
    await session.delete(target)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{target_id}/checks",
    response_model=CheckResultRead,
    status_code=status.HTTP_201_CREATED,
)
async def check_target(
    target_id: UUID,
    session: Session,
    current_user: CurrentUser,
) -> CheckResult:
    """Run a manual check, including for targets disabled from scheduling."""
    target = await get_target_or_404(target_id, current_user.id, session)
    target_url = target.url
    await session.rollback()

    try:
        outcome = await monitor_url(target_url)
    except UnsafeTargetError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    target_exists = await session.scalar(
        select(Target.id).where(
            Target.id == target_id,
            Target.owner_id == current_user.id,
        )
    )
    if target_exists is None:
        raise HTTPException(
            status_code=409,
            detail="Target was deleted while the check was running",
        )

    result = CheckResult(target_id=target_id, **asdict(outcome))
    session.add(result)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Target was deleted while the check was running",
        ) from error
    await session.refresh(result)
    return result
