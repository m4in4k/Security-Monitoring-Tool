"""CRUD endpoints for monitored targets."""

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import CheckResult, Target
from app.monitoring import UnsafeTargetError, monitor_url
from app.schemas import CheckResultRead, TargetCreate, TargetRead, TargetUpdate


router = APIRouter(prefix="/targets", tags=["targets"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def get_target_or_404(target_id: UUID, session: AsyncSession) -> Target:
    target = await session.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.get("", response_model=list[TargetRead])
async def list_targets(session: Session) -> list[TargetRead]:
    """Return monitored targets and their latest persisted checks."""
    result = await session.scalars(select(Target).order_by(Target.created_at.desc()))
    targets = list(result)
    if not targets:
        return []

    check_result = await session.scalars(
        select(CheckResult)
        .where(CheckResult.target_id.in_([target.id for target in targets]))
        .order_by(CheckResult.target_id, CheckResult.checked_at.desc())
    )
    latest_checks: dict[UUID, CheckResultRead] = {}
    for check in check_result:
        latest_checks.setdefault(check.target_id, CheckResultRead.model_validate(check))

    return [
        TargetRead.model_validate(target).model_copy(
            update={"latest_check": latest_checks.get(target.id)}
        )
        for target in targets
    ]


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
async def create_target(payload: TargetCreate, session: Session) -> Target:
    """Create an authorized monitoring target."""
    target = Target(**payload.model_dump())
    session.add(target)
    try:
        await session.flush()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Target URL already exists") from error
    await session.commit()
    await session.refresh(target)
    return target


@router.get("/{target_id}", response_model=TargetRead)
async def read_target(target_id: UUID, session: Session) -> Target:
    """Return one monitored target."""
    return await get_target_or_404(target_id, session)


@router.patch("/{target_id}", response_model=TargetRead)
async def update_target(
    target_id: UUID,
    payload: TargetUpdate,
    session: Session,
) -> Target:
    """Update selected fields on a monitored target."""
    target = await get_target_or_404(target_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    try:
        await session.flush()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Target URL already exists") from error
    await session.commit()
    await session.refresh(target)
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: UUID, session: Session) -> Response:
    """Delete a target and its monitoring history."""
    target = await get_target_or_404(target_id, session)
    await session.delete(target)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{target_id}/checks",
    response_model=CheckResultRead,
    status_code=status.HTTP_201_CREATED,
)
async def check_target(target_id: UUID, session: Session) -> CheckResult:
    """Run and persist one bounded, SSRF-protected monitoring check."""
    target = await get_target_or_404(target_id, session)
    target_url = target.url
    await session.rollback()

    try:
        outcome = await monitor_url(target_url)
    except UnsafeTargetError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    result = CheckResult(target_id=target_id, **asdict(outcome))
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result
