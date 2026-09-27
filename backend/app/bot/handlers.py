from __future__ import annotations

import re
from contextlib import suppress
from datetime import datetime

import structlog
from maxapi import Router
from maxapi.enums.chat_type import ChatType
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.auth.users import upsert_user
from app.bot import commands, keyboards, relay, urgent
from app.bot.runtime import get_transport
from app.bot.transport import MaxApiError, MaxRetryableError
from app.clock import current_time
from app.db import session as db
from app.db.models import MaxChat, Org, OrgInvite, OrgMember, User

log = structlog.get_logger("bot")

GREETING = (
    "Привет! Я помогу найти доброе дело, которое влезет в твоё свободное окно "
    "вместе с дорогой, напомню о нём и начислю часы в справку."
)
ORG_INVITE_OK = "Готово: теперь ты координатор организации «{name}». Смены — в приложении."
ORG_INVITE_ERRORS = {
    "invite_not_found": "Приглашение не найдено. Попроси владельца организации прислать новое.",
    "invite_expired": "Срок приглашения истёк. Попроси владельца организации прислать новое.",
    "invite_used": "Это приглашение уже использовано. Попроси владельца прислать новое.",
    "org_not_verified": "Организация ещё не прошла проверку — приглашение сработает после неё.",
    "member_revoked": (
        "Извини, доступ к этой организации у тебя сейчас закрыт. "
        "Если это ошибка, попроси владельца организации вернуть его в разделе «Доступы»."
    ),
}
ORG_INVITE_FAILED = "Не получилось принять приглашение. Попробуй позже."
ORG_PREFIX = "org_"

def build_router() -> Router:
    router = Router("vremya")
    router.bot_started()(on_bot_started)
    router.message_created()(on_message)
    router.message_callback()(on_callback)
    return router

async def on_bot_started(event: BotStarted) -> None:
    await start(event.user.user_id, event.user.first_name, event.chat_id, event.payload)

async def on_message(event: MessageCreated) -> None:
    message = event.message
    sender = message.sender
    if sender is None or sender.is_bot or message.recipient.chat_type != ChatType.DIALOG:
        return
    chat_id = message.recipient.chat_id
    if chat_id is None:
        return
    text = (message.body.text if message.body is not None else None) or ""
    if text == "/start" or text.startswith("/start "):
        payload = text.removeprefix("/start").strip() or None
        await start(sender.user_id, sender.first_name, chat_id, payload)
        return
    if text.startswith("/"):
        command = text.split()[0].removeprefix("/")
        await commands.respond(
            command, max_user_id=sender.user_id, first_name=sender.first_name, chat_id=chat_id
        )
        return
    await relay.on_incoming(message, sender, chat_id)

async def on_callback(event: MessageCallback) -> None:
    payload = event.callback.payload or ""
    if payload.startswith(("menu:", keyboards.CONTACT_PREFIX, keyboards.BOOKING_PREFIX)):
        if event.message is None or event.message.recipient.chat_type != ChatType.DIALOG:
            return
        chat_id = event.message.recipient.chat_id
        if chat_id is None:
            return
        await commands.respond(
            payload.removeprefix("menu:"),
            max_user_id=event.callback.user.user_id,
            first_name=event.callback.user.first_name,
            chat_id=chat_id,
        )
        with suppress(MaxApiError):
            await get_transport().answer_callback(event.callback.callback_id, notification="Готово")
        return
    if payload.startswith(keyboards.URGENT_GO_PREFIX):
        chat_id = event.message.recipient.chat_id if event.message is not None else None
        await urgent.respond(
            callback_id=event.callback.callback_id,
            max_user_id=event.callback.user.user_id,
            first_name=event.callback.user.first_name,
            chat_id=chat_id,
            call_id=payload.removeprefix(keyboards.URGENT_GO_PREFIX),
        )

async def start(
    max_user_id: int, first_name: str | None, chat_id: int, payload: str | None
) -> None:
    if payload and (payload.startswith("contact_") or payload in ("my", "messages", "help")):
        await commands.respond(
            payload.replace("contact_", keyboards.CONTACT_PREFIX, 1),
            max_user_id=max_user_id,
            first_name=first_name,
            chat_id=chat_id,
        )
        return
    now = current_time()
    reply: str | None = None
    async with db.transaction() as session:
        user = await upsert_user(session, max_user_id, first_name)
        await session.flush()
        await session.execute(
            pg_insert(MaxChat)
            .values(user_id=user.id, chat_id=chat_id)
            .on_conflict_do_update(index_elements=[MaxChat.user_id], set_={"chat_id": chat_id})
        )
        await commands.select_conversation(session, user.id, None)
        if payload and payload.startswith(ORG_PREFIX):
            reply = await _accept_org_invite(session, payload, user, now)
    transport = get_transport()
    destination = payload.removeprefix("app_") if payload and payload.startswith("app_") else ""
    continuation = re.fullmatch(r"(?:my|(?:deal|fr|tr|co|org)_[A-Za-z0-9_-]+)", destination)
    attachment = (
        keyboards.open_app("Продолжить в приложении", destination)
        if continuation
        else keyboards.menu()
    )
    try:
        await transport.send_message(chat_id=chat_id, text=GREETING, attachments=[attachment])
        if reply is not None:
            await transport.send_message(chat_id=chat_id, text=reply)
    except MaxRetryableError:
        raise
    except MaxApiError as exc:
        log.warning("bot_reply_failed", status=exc.status, code=exc.code)

async def _accept_org_invite(session: AsyncSession, payload: str, user: User, now: datetime) -> str:
    from app.domain.org_access import accept_org_invite

    try:
        async with session.begin_nested():
            org = await accept_org_invite(session, payload, user, now)
    except ApiError as exc:
        if exc.code == "invite_used":
            joined = await _joined_by_invite(session, payload, user)
            if joined is not None:
                return ORG_INVITE_OK.format(name=joined.name)
        log.info("org_invite_declined", code=exc.code, user_id=str(user.id))
        return ORG_INVITE_ERRORS.get(exc.code, ORG_INVITE_FAILED)
    log.info("org_invite_accepted", org_id=str(org.id), user_id=str(user.id))
    return ORG_INVITE_OK.format(name=org.name)

async def _joined_by_invite(session: AsyncSession, payload: str, user: User) -> Org | None:
    invite = await session.scalar(
        select(OrgInvite).where(OrgInvite.token == payload.removeprefix(ORG_PREFIX))
    )
    if invite is None:
        return None
    member = await session.get(OrgMember, (invite.org_id, user.id))
    if member is None or member.revoked_at is not None:
        return None
    return await session.get(Org, invite.org_id)
