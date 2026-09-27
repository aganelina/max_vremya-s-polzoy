from datetime import timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.transport import MaxRetryableError
from app.bot.updates import JOB_KIND
from app.bot.webhook import SECRET_HEADER
from app.db.enums import OrgRole, OrgStatus
from app.db.models import BotUpdate, Job, MaxChat, OrgInvite, OrgMember, User
from tests.bot.conftest import (
    WEBHOOK_SECRET,
    BotHarness,
    bot_started,
    message_created,
    now,
    run_bot_updates,
)
from tests.factories import make_org


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")

async def test_bad_secret_rejected(app: FastAPI, harness: BotHarness) -> None:
    async with client_for(app) as client:
        missing = await client.post("/max/webhook", json=bot_started(user_id=1, chat_id=2))
        wrong = await client.post(
            "/max/webhook",
            json=bot_started(user_id=1, chat_id=2),
            headers={SECRET_HEADER: "not-the-secret"},
        )
    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert harness.transport.sent == []

async def _post(app: FastAPI, event: dict[str, object]) -> int:
    async with client_for(app) as client:
        response = await client.post(
            "/max/webhook", json=event, headers={SECRET_HEADER: WEBHOOK_SECRET}
        )
    return response.status_code

async def _bot_jobs(session: AsyncSession) -> list[Job]:
    session.expire_all()
    return list(await session.scalars(select(Job).where(Job.kind == JOB_KIND)))

async def test_webhook_stores_update_and_enqueues_job(
    app: FastAPI, harness: BotHarness, db_session: AsyncSession
) -> None:
    event = bot_started(user_id=4240, chat_id=770)
    assert await _post(app, event) == 200

    [job] = await _bot_jobs(db_session)
    assert job.payload == {"update": event} and job.done_at is None
    assert await db_session.scalar(select(func.count()).select_from(BotUpdate)) == 1
    assert harness.transport.sent == []

    assert await run_bot_updates()
    assert [m.chat_id for m in harness.transport.sent] == [770]

async def test_repeated_delivery_enqueues_one_job(
    app: FastAPI, harness: BotHarness, db_session: AsyncSession
) -> None:
    event = message_created("/start", user_id=4241, chat_id=771)
    assert await _post(app, event) == 200
    assert await _post(app, event) == 200
    assert len(await _bot_jobs(db_session)) == 1
    assert await run_bot_updates()
    assert await _post(app, event) == 200
    assert len(await _bot_jobs(db_session)) == 1
    assert len(harness.transport.sent) == 1

async def test_handler_failure_is_retried(
    app: FastAPI, harness: BotHarness, db_session: AsyncSession
) -> None:
    harness.transport.failures.append(MaxRetryableError(503, "connection_error"))
    assert await _post(app, bot_started(user_id=4239, chat_id=769)) == 200

    assert not await run_bot_updates()
    [job] = await _bot_jobs(db_session)
    assert job.attempts == 1 and job.last_error == "MaxRetryableError"
    assert job.done_at is None and job.run_at > now()
    assert harness.transport.sent == []

    assert await run_bot_updates(job.run_at + timedelta(seconds=1))
    assert [m.chat_id for m in harness.transport.sent] == [769]
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1

async def test_invite_accept_is_idempotent_on_retry(
    app: FastAPI, harness: BotHarness, db_session: AsyncSession
) -> None:
    org_id = (await make_org(db_session, status=OrgStatus.VERIFIED)).id
    db_session.add(OrgInvite(org_id=org_id, token="tok_rt", expires_at=now() + timedelta(days=7)))
    await db_session.commit()
    event = message_created("/start org_tok_rt", user_id=4238, chat_id=768)
    assert await _post(app, event) == 200

    original = harness.transport.send_message
    calls = 0

    async def flaky(**kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MaxRetryableError(503, "connection_error")
        return await original(**kwargs)  # type: ignore[arg-type]

    harness.transport.send_message = flaky  # type: ignore[method-assign]
    assert not await run_bot_updates()
    [job] = await _bot_jobs(db_session)
    assert await run_bot_updates(job.run_at + timedelta(seconds=1))

    assert "координатор" in harness.transport.texts[-1]
    user = await db_session.scalar(select(User).where(User.max_user_id == 4238))
    assert user is not None
    member = await db_session.get(OrgMember, (org_id, user.id))
    assert member is not None and member.role == OrgRole.COORDINATOR
    joined = await db_session.scalar(
        select(func.count()).select_from(Job).where(Job.kind == "notify.coordinator_joined")
    )
    assert joined == 1

async def test_bot_started_greets_and_saves_chat(
    app: FastAPI, harness: BotHarness, db_session: AsyncSession
) -> None:
    assert await _post(app, bot_started(user_id=4242, chat_id=777)) == 200
    assert await run_bot_updates()
    user = await db_session.scalar(select(User).where(User.max_user_id == 4242))
    assert user is not None and user.first_name == "Алина"
    chat = await db_session.get(MaxChat, user.id)
    assert chat is not None and chat.chat_id == 777
    [greeting] = harness.transport.sent
    assert greeting.chat_id == 777
    assert [b.text for b in greeting.buttons()] == [
        "Открыть приложение",
        "Мои записи",
        "Координатор",
        "Помощь",
    ]

async def test_unknown_update_type_is_acknowledged(app: FastAPI, harness: BotHarness) -> None:
    async with client_for(app) as client:
        response = await client.post(
            "/max/webhook",
            json={"update_type": "quantum_event", "timestamp": 1},
            headers={SECRET_HEADER: WEBHOOK_SECRET},
        )
    assert response.status_code == 200

async def test_duplicate_update_processed_once(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    event = message_created("/start", user_id=4243, chat_id=778)
    first = await harness.deliver(event)
    second = await harness.deliver(event)
    assert (first.duplicate, second.duplicate) == (False, True)
    assert len(harness.transport.sent) == 1
    assert await db_session.scalar(select(func.count()).select_from(BotUpdate)) == 1

async def test_start_with_org_invite_makes_coordinator(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    org = await make_org(db_session, status=OrgStatus.VERIFIED)
    invite = OrgInvite(org_id=org.id, token="tok_abc", expires_at=now() + timedelta(days=7))
    db_session.add(invite)
    await db_session.commit()

    await harness.deliver(message_created("/start org_tok_abc", user_id=4244, chat_id=779))

    user = await db_session.scalar(select(User).where(User.max_user_id == 4244))
    assert user is not None
    member = await db_session.get(OrgMember, (org.id, user.id))
    assert member is not None and member.role == OrgRole.COORDINATOR
    await db_session.refresh(invite)
    assert invite.used_at is not None
    assert "координатор" in harness.transport.texts[-1]

async def test_start_with_used_invite_explains(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    db_session.add(
        OrgInvite(org_id=org.id, token="used1", expires_at=now() + timedelta(days=1), used_at=now())
    )
    await db_session.commit()

    await harness.deliver(bot_started(user_id=4245, chat_id=780, payload="org_used1"))

    assert "уже использовано" in harness.transport.texts[-1]
    user = await db_session.scalar(select(User).where(User.max_user_id == 4245))
    assert user is not None
    assert await db_session.get(OrgMember, (org.id, user.id)) is None
