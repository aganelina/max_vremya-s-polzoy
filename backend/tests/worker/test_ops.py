from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session as db
from app.worker import ops
from app.worker.queue import enqueue, retry_delay, run_once
from tests.conftest import NOW


def test_retry_delay_is_exponential_and_capped() -> None:
    assert retry_delay(1) == timedelta(minutes=5)
    assert retry_delay(2) == timedelta(minutes=10)
    assert retry_delay(11) == timedelta(hours=1)

async def _boom(session: AsyncSession, payload: dict[str, Any]) -> None:
    raise RuntimeError("MAX недоступен")

async def test_job_exhausts_after_twelve_attempts_then_retry_requeues(
    db_session: AsyncSession,
) -> None:
    job = await enqueue(db_session, "notify.instructions", run_at=NOW)
    await db_session.commit()
    moment = NOW
    for _ in range(get_settings().worker_max_attempts):
        assert await run_once(moment, {"notify.instructions": _boom}) is True
        await db_session.refresh(job)
        moment = job.run_at
    assert job.done_at is not None and job.last_error == "exhausted:RuntimeError"
    assert job.done_at - NOW >= timedelta(hours=8)

    async with db.transaction() as session:
        [row] = await ops.status(session, job.done_at)
        found = await ops.backlog(session, job.done_at)
    assert (row.kind, row.exhausted_24h, row.pending) == ("notify.instructions", 1, 0)
    assert found.exhausted_last_hour == 1 and found.alarming

    async with db.transaction() as session:
        assert await ops.retry(session, job.done_at, kind="notify.other") == 0
        assert await ops.retry(session, job.done_at, kind="notify.instructions") == 1
    await db_session.refresh(job)
    assert (job.attempts, job.done_at, job.run_at) == (0, None, moment)

async def test_retry_revives_legacy_stuck_jobs(db_session: AsyncSession) -> None:
    job = await enqueue(db_session, "notify.certificate", run_at=NOW)
    job.attempts = get_settings().worker_max_attempts
    await db_session.commit()
    async with db.transaction() as session:
        [row] = await ops.status(session, NOW)
        assert row.stuck == 1
        assert await ops.retry(session, NOW) == 1
    await db_session.refresh(job)
    assert job.attempts == 0 and job.done_at is None

async def test_backlog_warns_on_many_due_jobs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(3):
        await enqueue(db_session, "notify.x", run_at=NOW)
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "worker_backlog_warn", 2)
    async with db.transaction() as session:
        found = await ops.backlog(session, NOW)
    assert found.due == 3 and found.alarming

async def test_readyz_needs_worker_heartbeat(app: FastAPI, db_session: AsyncSession) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with db.transaction() as session:
            await session.execute(text("DELETE FROM worker_heartbeat"))
        cold = await client.get("/readyz")
        await ops.Monitor().maybe_run(datetime.now(UTC))
        ready = await client.get("/readyz")
        health = await client.get("/healthz")
    assert cold.status_code == 503
    assert cold.json()["checks"]["worker"] == "fail: no heartbeat"
    assert cold.json()["checks"]["database"] == "ok"
    assert cold.json()["checks"]["migrations"] == "ok"
    assert ready.status_code == 200, ready.json()
    assert ready.json()["status"] == "ready"
    assert health.status_code == 200
    assert "/readyz" not in app.openapi()["paths"]
