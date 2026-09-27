from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.runtime import get_transport
from app.bot.transport import MaxApiError, MaxRetryableError, OutgoingAttachment
from app.config import get_settings
from app.db.enums import NotifyMode
from app.db.models import MaxChat, User

log = structlog.get_logger("bot")

class Audience(StrEnum):
    CRITICAL = "critical"
    DIRECT = "direct"
    MINE = "mine"
    ALL = "all"

def allowed(user: User, audience: Audience) -> bool:
    if audience in (Audience.CRITICAL, Audience.DIRECT):
        return True
    if user.notify == NotifyMode.PAUSE:
        return False
    if user.notify == NotifyMode.MINE:
        return audience is Audience.MINE
    return True

async def chat_id_of(session: AsyncSession, user_id: object) -> int | None:
    return await session.scalar(select(MaxChat.chat_id).where(MaxChat.user_id == user_id))

async def send(
    session: AsyncSession,
    user: User,
    text: str,
    audience: Audience,
    *,
    attachments: list[OutgoingAttachment] | None = None,
    kind: str = "",
) -> str | None:
    if not allowed(user, audience):
        log.info("bot_send_skipped", kind=kind, user_id=str(user.id), notify=user.notify.value)
        return None
    chat_id = await chat_id_of(session, user.id)
    try:
        return await get_transport().send_message(
            chat_id=chat_id,
            user_id=None if chat_id is not None else user.max_user_id,
            text=text,
            attachments=attachments,
        )
    except MaxRetryableError:
        raise
    except MaxApiError as exc:
        log.warning(
            "bot_send_failed", kind=kind, user_id=str(user.id), status=exc.status, code=exc.code
        )
        return None

async def send_file(
    session: AsyncSession,
    user: User,
    data: bytes,
    filename: str,
    caption: str,
    *,
    kind: str = "",
) -> str | None:
    chat_id = await chat_id_of(session, user.id)
    try:
        return await get_transport().send_file(
            chat_id=chat_id,
            user_id=None if chat_id is not None else user.max_user_id,
            data=data,
            filename=filename,
            text=caption,
        )
    except MaxRetryableError:
        raise
    except MaxApiError as exc:
        log.warning(
            "bot_send_failed", kind=kind, user_id=str(user.id), status=exc.status, code=exc.code
        )
        return None

async def send_to_chat(
    chat_id: int,
    text: str,
    *,
    kind: str = "",
    attachments: list[OutgoingAttachment] | None = None,
) -> str | None:
    try:
        return await get_transport().send_message(
            chat_id=chat_id, text=text, attachments=attachments
        )
    except MaxRetryableError:
        raise
    except MaxApiError as exc:
        log.warning("bot_send_failed", kind=kind, status=exc.status, code=exc.code)
        return None

_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

def local(moment: datetime) -> datetime:
    return moment.astimezone(get_settings().tz)

def fmt_time(moment: datetime) -> str:
    return local(moment).strftime("%H:%M")

def fmt_day(moment: datetime) -> str:
    value = local(moment)
    return f"{value.day} {_MONTHS[value.month - 1]}"

def fmt_day_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]}"

def fmt_when(moment: datetime) -> str:
    return f"{fmt_day(moment)}, {fmt_time(moment)}"

def fmt_hours(value: object) -> str:
    text = f"{float(str(value)):.1f}".replace(".", ",")
    return text.removesuffix(",0")
