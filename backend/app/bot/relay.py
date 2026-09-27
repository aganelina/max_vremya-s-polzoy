from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from maxapi.enums.message_link_type import MessageLinkType
from maxapi.types.message import Message as MaxMessage
from maxapi.types.users import User as MaxUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, notify
from app.bot.runtime import get_transport
from app.bot.transport import MaxApiError, MaxRetryableError
from app.clock import current_time
from app.db import session as db
from app.db.enums import BookingStatus, OrgStatus, RelayDirection, ShiftStatus
from app.db.models import (
    Booking,
    BotConversation,
    Message,
    MessageRelay,
    Org,
    OrgMember,
    Shift,
    User,
)
from app.worker.queue import enqueue_once

log = structlog.get_logger("bot")

REPLY_WINDOW = timedelta(hours=24)

DEFAULT_REPLY = (
    "Я присылаю напоминания и сообщения координаторов. "
    "/my — мои записи, /messages — написать координатору, /help — все возможности."
)
TEXT_TOO_LONG = "Сообщение слишком длинное. Отправь до 3000 символов одним сообщением."
TEXT_ONLY = "Пока я умею передавать только текст."
NOT_DELIVERED = "Не получилось передать сообщение. Попробуй позже."
REPLY_EXPIRED = (
    "Прошло больше суток после сообщения участника — ответ не передан. "
    "Написать участникам смены можно из приложения."
)
NOT_COORDINATOR = (
    "Извини, ответ не передан: у тебя больше нет доступа координатора к этой организации."
)

def coordinator_text(message: Message, shift: Shift) -> str:
    return f"Сообщение от координатора смены «{shift.title}»: {message.text}"

def forwarded_text(participant: User, shift: Shift, text: str) -> str:
    return f"{participant.first_name or 'Участник'} · {shift.title}\n{text}"

def answer_text(shift: Shift, text: str) -> str:
    return f"Ответ координатора смены «{shift.title}»: {text}"

async def on_incoming(message: MaxMessage, sender: MaxUser, chat_id: int) -> None:
    body = message.body
    text = ((body.text if body is not None else None) or "").strip()
    incoming_mid = body.mid if body is not None else None
    replied_mid: str | None = None
    if message.link is not None and message.link.type == MessageLinkType.REPLY:
        replied_mid = message.link.message.mid
    now = current_time()
    async with db.transaction() as session:
        user = await session.scalar(select(User).where(User.max_user_id == sender.user_id))
        reply = await _route(session, user, text, incoming_mid, replied_mid, now)
    if reply is not None:
        try:
            await get_transport().send_message(
                chat_id=chat_id,
                text=reply,
                attachments=[keyboards.menu()] if reply == DEFAULT_REPLY else None,
            )
        except MaxRetryableError:
            raise
        except MaxApiError as exc:
            log.warning("bot_reply_failed", status=exc.status, code=exc.code)

async def _route(
    session: AsyncSession,
    user: User | None,
    text: str,
    incoming_mid: str | None,
    replied_mid: str | None,
    now: datetime,
) -> str | None:
    if user is None:
        return DEFAULT_REPLY
    if len(text) > 3000:
        return TEXT_TOO_LONG
    if replied_mid is not None:
        to_participant = await session.scalar(
            select(MessageRelay)
            .where(
                MessageRelay.coordinator_mid == replied_mid,
                MessageRelay.coordinator_id == user.id,
                MessageRelay.direction == RelayDirection.TO_COORDINATOR,
            )
            .limit(1)
        )
        if to_participant is not None:
            if not text:
                return TEXT_ONLY
            return await _reply_to_participant(
                session, to_participant, user, text, incoming_mid, now
            )
        replied = await session.scalar(
            select(MessageRelay)
            .where(
                MessageRelay.participant_mid == replied_mid,
                MessageRelay.participant_id == user.id,
                MessageRelay.direction == RelayDirection.TO_PARTICIPANT,
            )
            .limit(1)
        )
    else:
        replied = None
    if replied_mid is not None and replied is None:
        return DEFAULT_REPLY
    conversation = await session.get(BotConversation, user.id) if replied_mid is None else None
    if conversation is not None:
        if conversation.relay_id is None or conversation.expires_at <= now:
            return DEFAULT_REPLY
        replied = await session.get(MessageRelay, conversation.relay_id)
    elif replied is None:
        replied = await session.scalar(
            select(MessageRelay)
            .where(
                MessageRelay.participant_id == user.id,
                MessageRelay.direction == RelayDirection.TO_PARTICIPANT,
                MessageRelay.created_at >= now - REPLY_WINDOW,
            )
            .order_by(MessageRelay.created_at.desc())
            .limit(1)
        )
    if replied is None or replied.coordinator_id is None:
        return DEFAULT_REPLY
    if replied.created_at < now - REPLY_WINDOW:
        return REPLY_EXPIRED
    if not await _can_relay(session, replied):
        return NOT_DELIVERED
    if not text:
        return TEXT_ONLY
    await enqueue_once(
        session,
        "relay.to_coordinator",
        {"relay_id": str(replied.id), "text": text, "incoming_mid": incoming_mid},
        dedup_key=f"relay.to_coordinator:{incoming_mid}" if incoming_mid else None,
    )
    return None

async def _reply_to_participant(
    session: AsyncSession,
    relay: MessageRelay,
    coordinator: User,
    text: str,
    incoming_mid: str | None,
    now: datetime,
) -> str | None:
    shift = await _shift_of(session, relay)
    if shift is None:
        return NOT_DELIVERED
    member = await session.get(OrgMember, (shift.org_id, coordinator.id))
    if member is None or member.revoked_at is not None:
        return NOT_COORDINATOR
    if relay.created_at < now - REPLY_WINDOW:
        return REPLY_EXPIRED
    if not await _can_relay(session, relay):
        return NOT_DELIVERED
    await enqueue_once(
        session,
        "relay.to_participant",
        {"relay_id": str(relay.id), "text": text, "incoming_mid": incoming_mid},
        dedup_key=f"relay.to_participant:{incoming_mid}" if incoming_mid else None,
    )
    return None

async def _relay_from(
    session: AsyncSession, payload: dict[str, Any]
) -> tuple[MessageRelay, str, str | None] | None:
    try:
        relay_id = uuid.UUID(str(payload["relay_id"]))
        text = str(payload["text"])
    except (KeyError, ValueError):
        return None
    relay = await session.get(MessageRelay, relay_id)
    if relay is None or not text:
        return None
    mid = payload.get("incoming_mid")
    return relay, text, str(mid) if mid is not None else None

async def relay_to_coordinator(session: AsyncSession, payload: dict[str, Any]) -> None:
    found = await _relay_from(session, payload)
    if found is None:
        return
    relay, text, incoming_mid = found
    participant = await session.get(User, relay.participant_id)
    if participant is None:
        return
    await _to_coordinator(session, relay, participant, text, incoming_mid, current_time())

async def relay_to_participant(session: AsyncSession, payload: dict[str, Any]) -> None:
    found = await _relay_from(session, payload)
    if found is None:
        return
    relay, text, incoming_mid = found
    await _to_participant(session, relay, text, incoming_mid, current_time())

async def _shift_of(session: AsyncSession, relay: MessageRelay) -> Shift | None:
    return await session.scalar(
        select(Shift)
        .join(Message, Message.shift_id == Shift.id)
        .where(Message.id == relay.message_id)
    )

async def _can_relay(session: AsyncSession, relay: MessageRelay) -> bool:
    shift = await _shift_of(session, relay)
    if shift is None or shift.status == ShiftStatus.CANCELLED:
        return False
    org = await session.get(Org, shift.org_id)
    member = await session.get(OrgMember, (shift.org_id, relay.coordinator_id))
    if org is None or org.status != OrgStatus.VERIFIED or member is None or member.revoked_at:
        return False
    booking = await session.scalar(
        select(Booking.id)
        .where(
            Booking.shift_id == shift.id,
            Booking.user_id == relay.participant_id,
            Booking.status != BookingStatus.CANCELLED,
        )
        .limit(1)
    )
    return booking is not None

async def _to_coordinator(
    session: AsyncSession,
    relay: MessageRelay,
    participant: User,
    text: str,
    incoming_mid: str | None,
    now: datetime,
) -> bool:
    coordinator = await session.get(User, relay.coordinator_id)
    shift = await _shift_of(session, relay)
    if coordinator is None or shift is None:
        return False
    if relay.created_at < now - REPLY_WINDOW or not await _can_relay(session, relay):
        return False
    mid = await notify.send(
        session,
        coordinator,
        forwarded_text(participant, shift, text),
        notify.Audience.DIRECT,
        kind="relay.to_coordinator",
    )
    if mid is None:
        return False
    session.add(
        MessageRelay(
            message_id=relay.message_id,
            participant_id=participant.id,
            coordinator_id=coordinator.id,
            participant_mid=incoming_mid,
            coordinator_mid=mid,
            direction=RelayDirection.TO_COORDINATOR,
            created_at=now,
        )
    )
    log.info("relay_to_coordinator", message_id=str(relay.message_id))
    return True

async def _to_participant(
    session: AsyncSession,
    relay: MessageRelay,
    text: str,
    incoming_mid: str | None,
    now: datetime,
) -> bool:
    participant = await session.get(User, relay.participant_id)
    shift = await _shift_of(session, relay)
    if participant is None or shift is None:
        return False
    if relay.created_at < now - REPLY_WINDOW or not await _can_relay(session, relay):
        return False
    mid = await notify.send(
        session,
        participant,
        answer_text(shift, text),
        notify.Audience.DIRECT,
        kind="relay.to_participant",
    )
    if mid is None:
        return False
    session.add(
        MessageRelay(
            message_id=relay.message_id,
            participant_id=participant.id,
            coordinator_id=relay.coordinator_id,
            participant_mid=mid,
            coordinator_mid=incoming_mid,
            direction=RelayDirection.TO_PARTICIPANT,
            created_at=now,
        )
    )
    log.info("relay_to_participant", message_id=str(relay.message_id))
    return True
