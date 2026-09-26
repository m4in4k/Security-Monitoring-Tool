"""Reusable retention maintenance for historical monitoring results."""

import asyncio
from datetime import UTC, datetime, timedelta
import sys

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionFactory, engine
from app.models import CheckResult


async def prune_expired_check_results(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
) -> int:
    """Delete results outside the retention window and return the row count."""
    days = (
        retention_days
        if retention_days is not None
        else get_settings().history_retention_days
    )
    if days < 1:
        raise ValueError("retention_days must be at least 1")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = await session.execute(
        delete(CheckResult).where(CheckResult.checked_at < cutoff)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def run_retention_maintenance() -> int:
    """Apply retention in its own transaction for a worker or maintenance job."""
    async with SessionFactory() as session:
        deleted = await prune_expired_check_results(session)
        await session.commit()
        return deleted


def main() -> None:
    """Run history retention as a standalone maintenance command."""
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            deleted = runner.run(run_retention_maintenance())
        print(f"Deleted {deleted} expired monitoring result(s).")
    finally:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(engine.dispose())


if __name__ == "__main__":
    main()
