from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import MicroAnswerStatus, OrgStatus
from app.db.models import MicroAnswer
from tests.conftest import NOW
from tests.engagement.helpers import make_task
from tests.factories import make_org, make_user
from tests.support import dev

MICRO_KEYS = {"id", "title", "org", "minutes", "text", "status", "deadline", "answer"}

async def test_next_skip_and_filters(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    pending = await make_org(db_session, status=OrgStatus.PENDING)
    t1 = await make_task(db_session, org, title="Первое", created_at=NOW - timedelta(days=2))
    t2 = await make_task(db_session, org, title="Второе", created_at=NOW - timedelta(days=1))
    await make_task(db_session, org, title="Выключено", active=False)
    await make_task(db_session, pending, title="Не проверено")
    user = await make_user(db_session)

    resp = await client.get("/micro-tasks/next", headers=dev(user))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == MICRO_KEYS
    assert body["id"] == str(t1.id)
    assert body["status"] == "free" and body["deadline"] is None and body["answer"] == ""
    assert body["org"] == {"id": str(org.id), "name": org.name, "verified": True}

    skipped = await client.get("/micro-tasks/next", params={"skip": str(t1.id)}, headers=dev(user))
    assert skipped.json()["id"] == str(t2.id)
    again = await client.get("/micro-tasks/next", params={"skip": str(t2.id)}, headers=dev(user))
    assert again.json()["id"] == str(t1.id)

async def test_next_without_tasks_404(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    resp = await client.get("/micro-tasks/next", headers=dev(user))
    assert resp.status_code == 404
    assert resp.json() == {"code": "no_micro_tasks"}

async def test_take_answer_flow(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    task = await make_task(db_session, org)
    other = await make_task(db_session, org)
    user = await make_user(db_session)

    taken = await client.post(f"/micro-tasks/{task.id}/take", headers=dev(user))
    assert taken.status_code == 200
    assert taken.json()["status"] == "taken"
    assert taken.json()["deadline"] == (NOW + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    nxt = await client.get("/micro-tasks/next", headers=dev(user))
    assert nxt.json()["id"] == str(task.id) and nxt.json()["status"] == "taken"
    assert (await client.post(f"/micro-tasks/{task.id}/take", headers=dev(user))).status_code == 200

    busy = await client.post(f"/micro-tasks/{other.id}/take", headers=dev(user))
    assert busy.status_code == 409
    assert busy.json() == {"code": "already_taken"}

    short = await client.post(
        f"/micro-tasks/{task.id}/answer", json={"answer": " коротко "}, headers=dev(user)
    )
    assert short.status_code == 422
    assert short.json() == {"code": "answer_too_short"}

    sent = await client.post(
        f"/micro-tasks/{task.id}/answer",
        json={"answer": "  Пять книг для подростков  "},
        headers=dev(user),
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["answer"] == "Пять книг для подростков"
    assert sent.json()["deadline"] is None

    nxt = await client.get("/micro-tasks/next", params={"skip": str(task.id)}, headers=dev(user))
    assert nxt.json()["id"] == str(other.id)
    assert (
        await client.post(f"/micro-tasks/{other.id}/take", headers=dev(user))
    ).status_code == 200

async def test_take_full_task(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    task = await make_task(db_session, org, answers_needed=1)
    first, second = await make_user(db_session), await make_user(db_session)
    assert (
        await client.post(f"/micro-tasks/{task.id}/take", headers=dev(first))
    ).status_code == 200
    resp = await client.post(f"/micro-tasks/{task.id}/take", headers=dev(second))
    assert resp.status_code == 409
    assert resp.json() == {"code": "already_taken"}
    assert (await client.get("/micro-tasks/next", headers=dev(second))).status_code == 404

async def test_release(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    task = await make_task(db_session, org)
    user = await make_user(db_session)
    missing = await client.delete(f"/micro-tasks/{task.id}/take", headers=dev(user))
    assert missing.status_code == 404

    await client.post(f"/micro-tasks/{task.id}/take", headers=dev(user))
    resp = await client.delete(f"/micro-tasks/{task.id}/take", headers=dev(user))
    assert resp.status_code == 204
    status = await db_session.scalar(
        select(MicroAnswer.status).where(MicroAnswer.task_id == task.id)
    )
    assert status is MicroAnswerStatus.RELEASED
    no_answer = await client.post(
        f"/micro-tasks/{task.id}/answer", json={"answer": "Достаточно длинный"}, headers=dev(user)
    )
    assert no_answer.status_code == 409

async def test_expired_take_is_released(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    old, fresh = await make_task(db_session, org), await make_task(db_session, org)
    user = await make_user(db_session)
    db_session.add(
        MicroAnswer(
            task_id=old.id,
            user_id=user.id,
            status=MicroAnswerStatus.TAKEN,
            deadline=NOW - timedelta(minutes=1),
        )
    )
    await db_session.commit()
    resp = await client.post(f"/micro-tasks/{fresh.id}/take", headers=dev(user))
    assert resp.status_code == 200

async def test_returned_shows_note(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    task = await make_task(db_session, org)
    user = await make_user(db_session)
    db_session.add(
        MicroAnswer(
            task_id=task.id,
            user_id=user.id,
            status=MicroAnswerStatus.RETURNED,
            answer="Первый вариант ответа",
            review_note="Добавь конкретики",
        )
    )
    await db_session.commit()
    body = (await client.get("/micro-tasks/next", headers=dev(user))).json()
    assert body["status"] == "returned" and body["reviewNote"] == "Добавь конкретики"
    sent = await client.post(
        f"/micro-tasks/{task.id}/answer", json={"answer": "Исправленный ответ"}, headers=dev(user)
    )
    assert sent.json()["status"] == "sent"

async def test_requires_onboarding(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, onboarded=False)
    resp = await client.get("/micro-tasks/next", headers=dev(user))
    assert resp.status_code == 403

async def test_concurrent_take_respects_answers_needed(db_session: AsyncSession) -> None:
    import asyncio

    import pytest

    from app.api.errors import Conflict
    from app.db import session as db
    from app.domain.micro import take_task

    org = await make_org(db_session)
    task = await make_task(db_session, org, answers_needed=1)
    first, second = await make_user(db_session), await make_user(db_session)
    task_id, first_id, second_id = task.id, first.id, second.id

    maker = db.get_sessionmaker()
    async with maker() as s1, maker() as s2:
        await take_task(s1, first_id, task_id, NOW)
        waiting = asyncio.create_task(take_task(s2, second_id, task_id, NOW))
        await asyncio.sleep(0.3)
        assert not waiting.done()
        await s1.commit()
        with pytest.raises(Conflict) as exc:
            await waiting
        assert exc.value.code == "already_taken"
        await s2.rollback()

    taken = await db_session.scalar(
        select(func.count()).select_from(MicroAnswer).where(MicroAnswer.task_id == task_id)
    )
    assert taken == 1
