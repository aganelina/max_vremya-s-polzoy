from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.relay import NOT_COORDINATOR, REPLY_EXPIRED
from app.bot.transport import MaxRetryableError
from app.db.enums import BookingStatus, MessageAudience, RelayDirection
from app.db.models import Booking, Job, Message, MessageRelay
from app.worker.queue import enqueue, run_once
from tests.bot.conftest import BotHarness, drain, make_shift, message_created, now, with_chat
from tests.factories import add_member, make_org, make_user


async def _setup(db_session: AsyncSession, audience: MessageAudience = MessageAudience.ALL):
    org = await make_org(db_session)
    coordinator = await make_user(db_session, first_name="Ольга")
    await add_member(db_session, org, coordinator)
    going = await make_user(db_session, first_name="Алина")
    came = await make_user(db_session, first_name="Тимур")
    coord_chat = await with_chat(db_session, coordinator)
    going_chat = await with_chat(db_session, going)
    came_chat = await with_chat(db_session, came)
    shift = await make_shift(db_session, org)
    db_session.add_all(
        [
            Booking(shift_id=shift.id, user_id=going.id, status=BookingStatus.GOING),
            Booking(shift_id=shift.id, user_id=came.id, status=BookingStatus.CHECKED_IN),
        ]
    )
    message = Message(
        shift_id=shift.id, audience=audience, text="Вход со двора", created_by=coordinator.id
    )
    db_session.add(message)
    await db_session.flush()
    await enqueue(db_session, "notify.coord_message", {"message_id": str(message.id)})
    await db_session.commit()
    return message, (coordinator, coord_chat), (going, going_chat), (came, came_chat)

async def test_coord_message_goes_to_audience_with_relays(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    message, _, (going, going_chat), (_, came_chat) = await _setup(
        db_session, MessageAudience.WAITING
    )
    await drain()

    [sent] = harness.transport.sent
    assert sent.chat_id == going_chat
    assert sent.text == "Сообщение от координатора смены «Разбор книг»: Вход со двора"
    assert harness.transport.to_chat(came_chat) == []
    relay = (await db_session.scalars(select(MessageRelay))).one()
    assert relay.participant_id == going.id
    assert relay.participant_mid == sent.mid
    assert relay.direction == RelayDirection.TO_PARTICIPANT

    await enqueue(db_session, "notify.coord_message", {"message_id": str(message.id)})
    await db_session.commit()
    await drain()
    assert len(harness.transport.sent) == 1

async def test_reply_relayed_both_ways(harness: BotHarness, db_session: AsyncSession) -> None:
    _, (coordinator, coord_chat), (going, going_chat), _ = await _setup(db_session)
    await drain()
    to_alina = harness.transport.to_chat(going_chat)[0]
    harness.transport.reset()

    await harness.deliver(
        message_created(
            "Опоздаю на 5 минут",
            user_id=going.max_user_id,
            chat_id=going_chat,
            reply_to=to_alina.mid,
        )
    )
    assert harness.transport.sent == []
    await drain()
    [forwarded] = harness.transport.sent
    assert forwarded.chat_id == coord_chat
    assert forwarded.text == "Алина · Разбор книг\nОпоздаю на 5 минут"
    harness.transport.reset()

    await harness.deliver(
        message_created(
            "Хорошо, ждём",
            user_id=coordinator.max_user_id,
            chat_id=coord_chat,
            reply_to=forwarded.mid,
        )
    )
    await drain()
    [answer] = harness.transport.sent
    assert answer.chat_id == going_chat
    assert answer.text == "Ответ координатора смены «Разбор книг»: Хорошо, ждём"

async def test_plain_message_within_24h_is_relayed(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    _, (_, coord_chat), (going, going_chat), _ = await _setup(db_session)
    await drain()
    harness.transport.reset()

    await harness.deliver(
        message_created("А где парковка?", user_id=going.max_user_id, chat_id=going_chat)
    )
    await drain()
    [forwarded] = harness.transport.sent
    assert forwarded.chat_id == coord_chat

async def test_message_after_24h_gets_default_reply(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    _, (_, coord_chat), (going, going_chat), _ = await _setup(db_session)
    await drain()
    for relay in await db_session.scalars(select(MessageRelay)):
        relay.created_at = now() - timedelta(hours=25)
    await db_session.commit()
    harness.transport.reset()

    await harness.deliver(message_created("Привет", user_id=going.max_user_id, chat_id=going_chat))
    [reply] = harness.transport.sent
    assert reply.chat_id == going_chat
    assert harness.transport.to_chat(coord_chat) == []

async def _forwarded_to_coordinator(harness: BotHarness, db_session: AsyncSession):
    _, (coordinator, coord_chat), (going, going_chat), _ = await _setup(db_session)
    await drain()
    to_alina = harness.transport.to_chat(going_chat)[0]
    await harness.deliver(
        message_created(
            "Опоздаю", user_id=going.max_user_id, chat_id=going_chat, reply_to=to_alina.mid
        )
    )
    await drain()
    forwarded = harness.transport.to_chat(coord_chat)[-1]
    harness.transport.reset()
    return coordinator, coord_chat, going_chat, forwarded

async def test_revoked_coordinator_reply_not_relayed(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    from app.db.models import OrgMember

    coordinator, coord_chat, going_chat, forwarded = await _forwarded_to_coordinator(
        harness, db_session
    )
    member = (
        await db_session.scalars(select(OrgMember).where(OrgMember.user_id == coordinator.id))
    ).one()
    member.revoked_at = now()
    await db_session.commit()

    await harness.deliver(
        message_created(
            "Ждём", user_id=coordinator.max_user_id, chat_id=coord_chat, reply_to=forwarded.mid
        )
    )
    await drain()
    assert harness.transport.to_chat(going_chat) == []
    [reply] = harness.transport.to_chat(coord_chat)
    assert reply.text == NOT_COORDINATOR

async def test_coordinator_reply_after_24h_not_relayed(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    coordinator, coord_chat, going_chat, forwarded = await _forwarded_to_coordinator(
        harness, db_session
    )
    for relay in await db_session.scalars(select(MessageRelay)):
        relay.created_at = now() - timedelta(hours=25)
    await db_session.commit()

    await harness.deliver(
        message_created(
            "Ждём", user_id=coordinator.max_user_id, chat_id=coord_chat, reply_to=forwarded.mid
        )
    )
    await drain()
    assert harness.transport.to_chat(going_chat) == []
    [reply] = harness.transport.to_chat(coord_chat)
    assert reply.text == REPLY_EXPIRED

async def test_relay_rate_limited_is_retried(harness: BotHarness, db_session: AsyncSession) -> None:
    _, (_, coord_chat), (going, going_chat), _ = await _setup(db_session)
    await drain()
    harness.transport.reset()
    harness.transport.failures.append(MaxRetryableError(429, "too.many.requests"))

    await harness.deliver(
        message_created("А где парковка?", user_id=going.max_user_id, chat_id=going_chat)
    )
    await drain()
    assert harness.transport.to_chat(coord_chat) == []
    job = (await db_session.scalars(select(Job).where(Job.kind == "relay.to_coordinator"))).one()
    await db_session.refresh(job)
    assert job.done_at is None and job.attempts == 1

    assert await run_once(now() + timedelta(hours=1))
    [forwarded] = harness.transport.to_chat(coord_chat)
    assert forwarded.text == "Алина · Разбор книг\nА где парковка?"
