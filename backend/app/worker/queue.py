from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import session as db
from app.db.models import Job

if TYPE_CHECKING:
    from app.worker.jobs import JobHandler

log = structlog.get_logger("worker")

async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    run_at: datetime | None = None,
) -> Job:
    job = Job(kind=kind, payload=payload or {})
    if run_at is not None:
        job.run_at = run_at
    session.add(job)
    await session.flush()
    return job

async def enqueue_once(
    session: AsyncSession, kind: str, payload: dict[str, Any], dedup_key: str | None
) -> bool:
    if dedup_key is None:
        await enqueue(session, kind, payload)
        return True
    stmt = (
        pg_insert(Job)
        .values(kind=kind, payload=payload, dedup_key=dedup_key)
        .on_conflict_do_nothing(
            index_elements=[Job.dedup_key], index_where=text("dedup_key IS NOT NULL")
        )
        .returning(Job.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None

EXHAUSTED_PREFIX = "exhausted:"
SCRUB_KINDS = frozenset({"bot.update", "relay.to_coordinator", "relay.to_participant"})
RECOVERY_WINDOW = timedelta(days=7)

def _scrub(job: Job) -> None:
    if job.kind in SCRUB_KINDS:
        job.payload = {}

def retry_delay(attempts: int, settings: Settings | None = None) -> timedelta:
    settings = settings or get_settings()
    seconds = settings.worker_retry_base_seconds * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, settings.worker_retry_max_seconds))

async def run_once(
    now: datetime,
    handlers: dict[str, JobHandler] | None = None,
    *,
    kinds: Collection[str] | None = None,
) -> bool:
    if handlers is None:
        from app.worker.jobs import HANDLERS

        handlers = HANDLERS
    settings = get_settings()
    async with db.transaction() as session:
        query = select(Job).where(
            Job.done_at.is_(None),
            Job.run_at <= now,
            Job.attempts < settings.worker_max_attempts,
        )
        if kinds is not None:
            query = query.where(Job.kind.in_(list(kinds)))
        job = await session.scalar(
            query.order_by(Job.run_at).limit(1).with_for_update(skip_locked=True)
        )
        if job is None:
            return False
        handler = handlers.get(job.kind)
        if handler is None:
            job.attempts += 1
            log.warning("job_unknown_kind", job_id=str(job.id), kind=job.kind)
            if job.attempts >= settings.worker_max_attempts:
                job.done_at = now
                job.last_error = f"{EXHAUSTED_PREFIX}unknown_kind"
            else:
                job.last_error = "unknown_kind"
                job.run_at = now + timedelta(hours=1)
            return True
        try:
            async with session.begin_nested():
                await handler(session, job.payload)
        except Exception as exc:
            job.attempts += 1
            error = type(exc).__name__
            if job.attempts >= settings.worker_max_attempts:
                job.done_at = now
                job.last_error = f"{EXHAUSTED_PREFIX}{error}"
                log.exception("job_exhausted", job_id=str(job.id), kind=job.kind)
                return True
            job.last_error = error
            job.run_at = now + retry_delay(job.attempts, settings)
            log.exception("job_failed", job_id=str(job.id), kind=job.kind, attempts=job.attempts)
        else:
            job.done_at = now
            _scrub(job)
            log.info("job_done", job_id=str(job.id), kind=job.kind)
        return True
