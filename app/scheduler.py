"""Standalone, database-coordinated scheduled monitoring worker."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import logging
import sys
from uuid import UUID, uuid4

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.database import SessionFactory, engine
from app.models import CheckResult, Target
from app.monitoring import MonitorOutcome, UnsafeTargetError, monitor_url


logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
Monitor = Callable[[str], Awaitable[MonitorOutcome]]
SessionMaker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class ClaimedTarget:
    """Immutable target data released from the claim transaction."""

    id: UUID
    url: str
    check_interval_seconds: int
    claim_token: UUID


def utc_now() -> datetime:
    """Return the current aware UTC time; replaceable in deterministic tests."""
    return datetime.now(UTC)


def next_check_time(claimed_at: datetime, interval_seconds: int) -> datetime:
    """Schedule the next normal occurrence without accumulating worker drift."""
    if claimed_at.utcoffset() is None:
        raise ValueError("claimed_at must be timezone-aware")
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be positive")
    return claimed_at + timedelta(seconds=interval_seconds)


def due_targets_statement(now: datetime, limit: int) -> Select[tuple[Target]]:
    """Build the ordered, locked query used to claim one due batch."""
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if limit < 1:
        raise ValueError("limit must be positive")
    return (
        select(Target)
        .where(
            Target.enabled.is_(True),
            Target.next_check_at <= now,
            or_(
                Target.scheduler_claimed_until.is_(None),
                Target.scheduler_claimed_until <= now,
            ),
        )
        .order_by(Target.next_check_at.asc(), Target.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


async def claim_due_targets(
    session_factory: SessionMaker,
    *,
    now: datetime,
    limit: int,
    claim_ttl_seconds: float,
) -> list[ClaimedTarget]:
    """Atomically reserve due occurrences and return detached work items."""
    if claim_ttl_seconds <= 0:
        raise ValueError("claim_ttl_seconds must be positive")
    async with session_factory() as session:
        targets = list(await session.scalars(due_targets_statement(now, limit)))
        claims: list[ClaimedTarget] = []
        for target in targets:
            claim_token = uuid4()
            target.scheduler_claim_token = claim_token
            target.scheduler_claimed_until = now + timedelta(
                seconds=claim_ttl_seconds
            )
            target.next_check_at = next_check_time(
                now,
                target.check_interval_seconds,
            )
            claims.append(
                ClaimedTarget(
                    target.id,
                    target.url,
                    target.check_interval_seconds,
                    claim_token,
                )
            )
        await session.commit()
        return claims


def retry_delay(settings: Settings, failed_attempt: int) -> float:
    """Return bounded exponential delay after a one-based failed attempt."""
    if failed_attempt < 1:
        raise ValueError("failed_attempt must be positive")
    return min(
        settings.scheduler_retry_base_seconds * (2 ** (failed_attempt - 1)),
        settings.scheduler_retry_max_seconds,
    )


def failed_outcome(error: BaseException) -> MonitorOutcome:
    """Convert an unexpected worker error into a persistable down result."""
    return MonitorOutcome(
        status="Down",
        http_status_code=None,
        response_time_ms=None,
        error_message=str(error) or error.__class__.__name__,
        tls_expires_at=None,
        security_score=None,
        security_findings={},
    )


async def monitor_with_retries(
    url: str,
    *,
    settings: Settings,
    monitor: Monitor = monitor_url,
    sleep: Sleep = asyncio.sleep,
) -> MonitorOutcome:
    """Run one target with bounded exponential backoff for down outcomes."""
    outcome: MonitorOutcome | None = None
    for attempt in range(1, settings.scheduler_max_attempts + 1):
        try:
            outcome = await monitor(url)
        except UnsafeTargetError as error:
            return failed_outcome(error)
        except Exception as error:
            logger.exception("Scheduled check attempt failed for %s", url)
            outcome = failed_outcome(error)

        if outcome.status != "Down" or attempt == settings.scheduler_max_attempts:
            return outcome
        await sleep(retry_delay(settings, attempt))

    raise AssertionError("retry loop completed without an outcome")


async def persist_result(
    session_factory: SessionMaker,
    claim: ClaimedTarget,
    outcome: MonitorOutcome,
    *,
    checked_at: datetime,
) -> bool:
    """Persist a result if its target still exists."""
    async with session_factory() as session:
        target = await session.scalar(
            select(Target)
            .where(
                Target.id == claim.id,
                Target.scheduler_claim_token == claim.claim_token,
            )
            .with_for_update()
        )
        if target is None:
            logger.info("Target %s was deleted or its claim expired", claim.id)
            return False
        target.scheduler_claim_token = None
        target.scheduler_claimed_until = None
        session.add(
            CheckResult(
                target_id=claim.id,
                checked_at=checked_at,
                **asdict(outcome),
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("Target %s was deleted before result persistence", claim.id)
            return False
        return True


async def execute_claim(
    claim: ClaimedTarget,
    *,
    session_factory: SessionMaker,
    settings: Settings,
    monitor: Monitor = monitor_url,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = utc_now,
) -> bool:
    """Check and persist one previously claimed scheduled occurrence."""
    outcome = await monitor_with_retries(
        claim.url,
        settings=settings,
        monitor=monitor,
        sleep=sleep,
    )
    return await persist_result(
        session_factory,
        claim,
        outcome,
        checked_at=clock(),
    )


async def run_scheduler_once(
    *,
    session_factory: SessionMaker = SessionFactory,
    settings: Settings | None = None,
    monitor: Monitor = monitor_url,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = utc_now,
) -> int:
    """Claim and process one due batch, returning persisted result count."""
    resolved_settings = settings or get_settings()
    claims = await claim_due_targets(
        session_factory,
        now=clock(),
        limit=min(
            resolved_settings.scheduler_batch_size,
            resolved_settings.scheduler_max_concurrency,
        ),
        claim_ttl_seconds=resolved_settings.scheduler_claim_ttl_seconds,
    )
    semaphore = asyncio.Semaphore(resolved_settings.scheduler_max_concurrency)

    async def bounded_execute(claim: ClaimedTarget) -> bool:
        async with semaphore:
            return await execute_claim(
                claim,
                session_factory=session_factory,
                settings=resolved_settings,
                monitor=monitor,
                sleep=sleep,
                clock=clock,
            )

    persisted = await asyncio.gather(*(bounded_execute(claim) for claim in claims))
    return sum(persisted)


async def run_scheduler(
    *,
    session_factory: SessionMaker = SessionFactory,
    settings: Settings | None = None,
    monitor: Monitor = monitor_url,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = utc_now,
) -> None:
    """Continuously poll for scheduled work in a dedicated worker process."""
    resolved_settings = settings or get_settings()
    while True:
        try:
            completed = await run_scheduler_once(
                session_factory=session_factory,
                settings=resolved_settings,
                monitor=monitor,
                sleep=sleep,
                clock=clock,
            )
            if completed:
                logger.info("Persisted %s scheduled check result(s)", completed)
        except Exception:
            logger.exception("Scheduled-check polling iteration failed")
        await sleep(resolved_settings.scheduler_poll_seconds)


def main() -> None:
    """Run the scheduler independently from all FastAPI processes."""
    logging.basicConfig(level=logging.INFO)
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(run_scheduler())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")
    finally:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(engine.dispose())


if __name__ == "__main__":
    main()
