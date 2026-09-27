from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.bot.runtime import get_transport
from app.bot.transport import MaxApiError, MaxRetryableError
from app.clock import current_time
from app.db import session as db
from app.db.models import UrgentCall, UrgentRecipient, User

log = structlog.get_logger("bot")

class Outcome(StrEnum):
    BOOKED = "booked"
    ALREADY = "already"
    SEAT_TAKEN = "seat_taken"
    TIME_CONFLICT = "time_conflict"
    GONE = "gone"

NOTIFICATIONS = {
    Outcome.BOOKED: "Записал! Спасибо, что откликнулся.",
    Outcome.ALREADY: "Ты уже записан на эту смену.",
    Outcome.SEAT_TAKEN: "Спасибо! Места уже заняты — в следующий раз обязательно.",
    Outcome.TIME_CONFLICT: "У тебя на это время уже есть запись — спасибо, что откликнулся!",
    Outcome.GONE: "Этот вызов уже неактуален. Спасибо!",
}

async def book(session: AsyncSession, call_id: str, max_user_id: int, now: datetime) -> Outcome:
    from app.domain.booking import create_booking

    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError:
        return Outcome.GONE
    call = await session.get(UrgentCall, call_uuid)
    user = await session.scalar(select(User).where(User.max_user_id == max_user_id))
    if call is None or user is None:
        return Outcome.GONE
    recipient = await session.get(UrgentRecipient, (call.id, user.id))
    if recipient is None:
        return Outcome.GONE
    try:
        async with session.begin_nested():
            _, created = await create_booking(session, user, call.shift_id, now)
    except ApiError as exc:
        return _BY_CODE.get(exc.code, Outcome.GONE)
    recipient.responded_at = recipient.responded_at or now
    return Outcome.BOOKED if created else Outcome.ALREADY

_BY_CODE = {"seat_taken": Outcome.SEAT_TAKEN, "time_conflict": Outcome.TIME_CONFLICT}

async def respond(
    *,
    callback_id: str,
    max_user_id: int,
    first_name: str | None,
    chat_id: int | None,
    call_id: str,
) -> Outcome:
    now = current_time()
    async with db.transaction() as session:
        outcome = await book(session, call_id, max_user_id, now)
    log.info("urgent_response", outcome=outcome.value)
    try:
        await get_transport().answer_callback(callback_id, notification=NOTIFICATIONS[outcome])
    except MaxRetryableError:
        raise
    except MaxApiError as exc:
        log.warning("bot_reply_failed", status=exc.status, code=exc.code)
    return outcome
