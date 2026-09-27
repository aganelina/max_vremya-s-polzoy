from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, and_, case, func, not_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session as db
from app.db.models import Job
from app.worker.queue import EXHAUSTED_PREFIX, SCRUB_KINDS

log = structlog.get_logger("worker")

HEARTBEAT_INTERVAL = timedelta(seconds=30)
HEARTBEAT_STALE_AFTER = timedelta(minutes=2)
BACKLOG_INTERVAL = timedelta(minutes=10)

async def beat(now: datetime) -> None:
    async with db.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO worker_heartbeat (id, beat_at) VALUES (1, :now) "
                "ON CONFLICT (id) DO UPDATE SET beat_at = EXCLUDED.beat_at"
            ),
            {"now": now},
        )

async def last_beat(session: AsyncSession) -> datetime | None:
    value = await session.scalar(text("SELECT beat_at FROM worker_heartbeat WHERE id = 1"))
    return value if isinstance(value, datetime) else None

def _exhausted() -> ColumnElement[bool]:
    return and_(Job.done_at.is_not(None), Job.last_error.startswith(EXHAUSTED_PREFIX))

@dataclass(frozen=True, slots=True)
class Backlog:
    due: int
    exhausted_last_hour: int

    @property
    def alarming(self) -> bool:
        return self.due > get_settings().worker_backlog_warn or self.exhausted_last_hour > 0

async def backlog(session: AsyncSession, now: datetime) -> Backlog:
    max_attempts = get_settings().worker_max_attempts
    due = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.done_at.is_(None), Job.run_at <= now, Job.attempts < max_attempts)
    )
    exhausted = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(_exhausted(), Job.done_at >= now - timedelta(hours=1))
    )
    return Backlog(due=due or 0, exhausted_last_hour=exhausted or 0)

class Monitor:

    def __init__(self) -> None:
        self._beat_at: datetime | None = None
        self._backlog_at: datetime | None = None

    async def maybe_run(self, now: datetime) -> None:
        if self._beat_at is None or now - self._beat_at >= HEARTBEAT_INTERVAL:
            self._beat_at = now
            try:
                await beat(now)
            except Exception:
                log.exception("worker_heartbeat_failed")
        if self._backlog_at is None or now - self._backlog_at >= BACKLOG_INTERVAL:
            self._backlog_at = now
            try:
                async with db.transaction() as session:
                    found = await backlog(session, now)
            except Exception:
                log.exception("jobs_backlog_check_failed")
                return
            if found.alarming:
                log.warning(
                    "jobs_backlog",
                    due=found.due,
                    exhausted_last_hour=found.exhausted_last_hour,
                    hint="python -m app.cli jobs-status",
                )

@dataclass(frozen=True, slots=True)
class KindStatus:
    kind: str
    pending: int
    failing: int
    stuck: int
    exhausted_24h: int

async def status(session: AsyncSession, now: datetime) -> list[KindStatus]:
    max_attempts = get_settings().worker_max_attempts
    open_ = Job.done_at.is_(None)

    def count(condition: ColumnElement[bool]) -> ColumnElement[int]:
        return func.sum(case((condition, 1), else_=0))

    rows = await session.execute(
        select(
            Job.kind,
            count(and_(open_, Job.attempts == 0)),
            count(and_(open_, Job.attempts > 0, Job.attempts < max_attempts)),
            count(and_(open_, Job.attempts >= max_attempts)),
            count(and_(_exhausted(), Job.done_at >= now - timedelta(days=1))),
        )
        .where(or_(open_, Job.done_at >= now - timedelta(days=1)))
        .group_by(Job.kind)
        .order_by(Job.kind)
    )
    result = [
        KindStatus(kind, int(p or 0), int(f or 0), int(s or 0), int(e or 0))
        for kind, p, f, s, e in rows.all()
    ]
    return [r for r in result if r.pending or r.failing or r.stuck or r.exhausted_24h]

async def retry(
    session: AsyncSession, now: datetime, *, kind: str | None = None, since_hours: float = 24
) -> int:
    max_attempts = get_settings().worker_max_attempts
    exhausted = and_(_exhausted(), Job.done_at >= now - timedelta(hours=since_hours))
    stuck = and_(Job.done_at.is_(None), Job.attempts >= max_attempts)
    scrubbed = and_(Job.kind.in_(SCRUB_KINDS), Job.payload == {})
    skipped_stmt = select(func.count()).select_from(Job).where(or_(exhausted, stuck), scrubbed)
    if kind is not None:
        skipped_stmt = skipped_stmt.where(Job.kind == kind)
    skipped = int(await session.scalar(skipped_stmt) or 0)
    if skipped:
        log.warning("jobs_retry_skipped_scrubbed", count=skipped, kind=kind)
    stmt = (
        update(Job)
        .where(or_(exhausted, stuck), not_(scrubbed))
        .values(attempts=0, done_at=None, run_at=now)
        .returning(Job.id)
    )
    if kind is not None:
        stmt = stmt.where(Job.kind == kind)
    ids = (await session.execute(stmt)).scalars().all()
    log.info("jobs_retried", count=len(ids), kind=kind)
    return len(ids)
