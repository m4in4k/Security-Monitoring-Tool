"""CRUD endpoints for monitored targets."""

from dataclasses import asdict
from datetime import datetime
from math import ceil
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.auth import CurrentUser
from app.models import CheckResult, Target, User
from app.monitoring import UnsafeTargetError, monitor_url
from app.retention import prune_expired_check_results
from app.schemas import (
    CheckResultRead,
    CheckHistoryPage,
    CheckHistorySummary,
    TargetCreate,
    TargetPage,
    TargetRead,
    TargetUpdate,
)


router = APIRouter(prefix="/targets", tags=["targets"])
Session = Annotated[AsyncSession, Depends(get_session)]
HISTORY_SERIES_MAX_POINTS = 500


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


def _validate_history_range(
    from_time: datetime | None,
    to_time: datetime | None,
) -> None:
    for name, value in (("from", from_time), ("to", to_time)):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must include a timezone offset",
            )
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(status_code=422, detail="from must be earlier than to")


@router.get("/{target_id}/checks", response_model=CheckHistoryPage)
async def list_target_checks(
    target_id: UUID,
    session: Session,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
) -> CheckHistoryPage:
    """Return filtered monitoring history and uptime aggregates for one target."""
    _validate_history_range(from_time, to_time)
    target = await get_target_read_or_404(target_id, current_user.id, session)

    filters = [CheckResult.target_id == target_id]
    if from_time is not None:
        filters.append(CheckResult.checked_at >= from_time)
    if to_time is not None:
        filters.append(CheckResult.checked_at < to_time)

    aggregate = (
        await session.execute(
            select(
                func.count(CheckResult.id),
                func.count(CheckResult.id).filter(
                    CheckResult.status.in_(("Healthy", "Warning"))
                ),
                func.avg(CheckResult.response_time_ms),
                func.min(CheckResult.response_time_ms),
                func.max(CheckResult.response_time_ms),
            ).where(*filters)
        )
    ).one()
    total = int(aggregate[0] or 0)
    available = int(aggregate[1] or 0)
    items = list(
        await session.scalars(
            select(CheckResult)
            .where(*filters)
            .order_by(CheckResult.checked_at.desc(), CheckResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    ranked_checks = (
        select(
            CheckResult.id.label("check_id"),
            func.row_number()
            .over(order_by=(CheckResult.checked_at.asc(), CheckResult.id.asc()))
            .label("position"),
        )
        .where(*filters)
        .subquery()
    )
    series_statement = select(CheckResult).join(
        ranked_checks,
        CheckResult.id == ranked_checks.c.check_id,
    )
    series_stride = 1
    if total > HISTORY_SERIES_MAX_POINTS:
        series_stride = ceil((total - 1) / (HISTORY_SERIES_MAX_POINTS - 1))
        series_statement = series_statement.where(
            or_(
                (ranked_checks.c.position - 1) % series_stride == 0,
                ranked_checks.c.position == total,
            )
        )
    series = list(
        await session.scalars(
            series_statement.order_by(
                CheckResult.checked_at.asc(),
                CheckResult.id.asc(),
            ).execution_options(
                history_series_stride=series_stride,
                history_series_total=total,
            )
        )
    )
    return CheckHistoryPage(
        target=target,
        items=items,
        series=series,
        summary=CheckHistorySummary(
            total_checks=total,
            available_checks=available,
            uptime_percentage=round((available / total) * 100, 3) if total else None,
            average_response_time_ms=(
                round(float(aggregate[2]), 2) if aggregate[2] is not None else None
            ),
            minimum_response_time_ms=aggregate[3],
            maximum_response_time_ms=aggregate[4],
        ),
        total=total,
        limit=limit,
        offset=offset,
    )


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
        await prune_expired_check_results(session)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Target was deleted while the check was running",
        ) from error
    await session.refresh(result)
    return result
