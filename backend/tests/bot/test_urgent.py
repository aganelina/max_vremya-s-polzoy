from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus
from app.db.models import Booking, UrgentCall, UrgentRecipient, User
from app.worker.queue import enqueue
from tests.bot.conftest import (
    BotHarness,
    drain,
    make_shift,
    message_callback,
    now,
    with_chat,
)
from tests.factories import make_org, make_user


async def _call(db_session: AsyncSession, capacity: int, users: list[User]) -> UrgentCall:
    org = await make_org(db_session)
    shift = await make_shift(
        db_session, org, starts_at=now() + timedelta(minutes=40), minutes=60, capacity=capacity
    )
    call = UrgentCall(
        org_id=org.id,
        shift_id=shift.id,
        what="Разгрузить машину",
        where_text="Склад на Баумана",
        start_in_min=40,
        people=capacity,
    )
    db_session.add(call)
    await db_session.flush()
    for user in users:
        db_session.add(UrgentRecipient(call_id=call.id, user_id=user.id))
    await enqueue(db_session, "notify.urgent_call", {"call_id": str(call.id)})
    await db_session.commit()
    return call

async def test_urgent_call_sent_with_go_button_and_books(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    alina = await make_user(db_session)
    chat = await with_chat(db_session, alina)
    call = await _call(db_session, capacity=1, users=[alina])

    await drain()
    [sent] = harness.transport.sent
    assert sent.chat_id == chat
    [button] = sent.buttons()
    assert button.text == "Иду"
    recipient = await db_session.get(UrgentRecipient, (call.id, alina.id))
    assert recipient is not None and recipient.sent_at is not None

    await harness.deliver(message_callback(button.payload, user_id=alina.max_user_id, chat_id=chat))

    booking = await db_session.scalar(select(Booking).where(Booking.user_id == alina.id))
    assert booking is not None and booking.status == BookingStatus.GOING
    await db_session.refresh(recipient)
    assert recipient.responded_at is not None
    assert harness.transport.callbacks[-1].notification.startswith("Записал")

async def test_urgent_seat_taken_is_polite(harness: BotHarness, db_session: AsyncSession) -> None:
    first = await make_user(db_session)
    second = await make_user(db_session)
    first_chat = await with_chat(db_session, first)
    second_chat = await with_chat(db_session, second)
    await _call(db_session, capacity=1, users=[first, second])
    await drain()
    payload = harness.transport.sent[0].buttons()[0].payload

    await harness.deliver(message_callback(payload, user_id=first.max_user_id, chat_id=first_chat))
    await harness.deliver(
        message_callback(payload, user_id=second.max_user_id, chat_id=second_chat)
    )

    assert harness.transport.callbacks[-1].notification.startswith("Спасибо! Места уже заняты")
    assert await db_session.scalar(select(Booking).where(Booking.user_id == second.id)) is None
