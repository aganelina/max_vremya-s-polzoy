from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Job
from app.worker.queue import enqueue, run_once
from tests.conftest import NOW


async def test_run_once_executes_due_job(db_session: AsyncSession) -> None:
    seen: list[dict[str, Any]] = []

    async def handler(session: AsyncSession, payload: dict[str, Any]) -> None:
        seen.append(payload)

    job = await enqueue(db_session, "ping", {"n": 1}, run_at=NOW - timedelta(seconds=1))
    await enqueue(db_session, "ping", {"n": 2}, run_at=NOW + timedelta(hours=1))
    await db_session.commit()

    assert await run_once(NOW, {"ping": handler}) is True
    assert await run_once(NOW, {"ping": handler}) is False
    assert seen == [{"n": 1}]
    await db_session.refresh(job)
    assert job.done_at == NOW

async def test_failed_and_unknown_jobs_are_retried_later(db_session: AsyncSession) -> None:
    async def boom(session: AsyncSession, payload: dict[str, Any]) -> None:
        raise RuntimeError("fail")

    failing = await enqueue(db_session, "boom", run_at=NOW)
    unknown = await enqueue(db_session, "later", run_at=NOW)
    await db_session.commit()

    assert await run_once(NOW, {"boom": boom}) is True
    assert await run_once(NOW, {"boom": boom}) is True
    assert await run_once(NOW, {"boom": boom}) is False
    for job in (failing, unknown):
        await db_session.refresh(job)
        assert job.done_at is None
        assert job.attempts == 1
        assert job.run_at > NOW
    assert failing.last_error == "RuntimeError"
    assert unknown.last_error == "unknown_kind"
    assert isinstance(failing, Job)

async def test_unknown_kind_is_closed_after_max_attempts(db_session: AsyncSession) -> None:
    job = await enqueue(db_session, "notify.typo", run_at=NOW)
    job.attempts = get_settings().worker_max_attempts - 1
    await db_session.commit()

    assert await run_once(NOW, {}) is True
    await db_session.refresh(job)
    assert job.done_at == NOW and job.last_error == "exhausted:unknown_kind"
    assert await run_once(NOW + timedelta(days=1), {}) is False
