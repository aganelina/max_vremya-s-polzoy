from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import structlog
from maxapi import Dispatcher
from maxapi.methods.types.getted_updates import process_update_webhook
from maxapi.types.error_event import ErrorEvent
from maxapi.types.updates import UpdateUnion
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.types.updates.message_created import MessageCreated
from maxapi.types.updates.message_edited import MessageEdited
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.transport import MaxNotConfiguredError
from app.db import session as db
from app.db.models import BotUpdate
from app.db.models.service import AccountTombstone
from app.worker.queue import enqueue

log = structlog.get_logger("bot")

JOB_KIND = "bot.update"

_handler_error: ContextVar[BaseException | None] = ContextVar("bot_handler_error", default=None)

def dedup_key(event: UpdateUnion) -> str:
    if isinstance(event, MessageCreated | MessageEdited):
        body = event.message.body
        chat_id = event.message.recipient.chat_id
        if body is not None and body.mid:
            suffix = f":{event.timestamp}" if isinstance(event, MessageEdited) else ""
            return f"{event.update_type}:{chat_id}:{body.mid}{suffix}"
    elif isinstance(event, MessageCallback):
        return f"message_callback:{event.callback.callback_id}"
    chat_id = getattr(event, "chat_id", None)
    user = getattr(event, "user", None)
    user_id = getattr(user, "user_id", None)
    if chat_id is not None or user_id is not None:
        return f"{event.update_type}:{chat_id}:{user_id}:{event.timestamp}"
    raw = json.dumps(event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return f"{event.update_type}:{hashlib.sha256(raw.encode()).hexdigest()}"

async def accept(event: UpdateUnion, raw: dict[str, Any]) -> bool:
    stmt = (
        pg_insert(BotUpdate)
        .values(dedup_key=dedup_key(event))
        .on_conflict_do_nothing(index_elements=[BotUpdate.dedup_key])
        .returning(BotUpdate.dedup_key)
    )
    async with db.transaction() as session:
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            log.info("bot_update_duplicate", update_type=str(event.update_type))
            return False
        await enqueue(session, JOB_KIND, {"update": raw})
    return True

class BotHandlerError(Exception):
    pass

async def dispatch(dispatcher: Dispatcher, event: UpdateUnion) -> None:
    token = _handler_error.set(None)
    try:
        await dispatcher.handle(event)
        error = _handler_error.get()
    except Exception as exc:
        error = exc
    finally:
        _handler_error.reset(token)
    if error is not None:
        log.warning("bot_handler_failed", update_type=str(event.update_type), reason=_reason(error))
        if isinstance(error, Exception):
            raise error
        raise BotHandlerError(_reason(error)) from error

async def handle_job(session: AsyncSession, payload: dict[str, Any]) -> None:
    from app.bot.runtime import get_runtime

    raw = payload.get("update")
    if not isinstance(raw, dict):
        log.warning("bot_update_bad_payload")
        return
    runtime = get_runtime()
    if runtime is None:
        raise MaxNotConfiguredError()
    event = await process_update_webhook(event_json=raw, bot=runtime.bot)
    if event is None:
        log.info("bot_update_unknown", update_type=str(raw.get("update_type")))
        return
    if await _from_deleted_account(session, event):
        log.info("bot_update_skipped", reason="account_deleted")
        return
    await dispatch(runtime.dispatcher, event)

def _event_user_id(event: UpdateUnion) -> int | None:
    message = getattr(event, "message", None)
    sender = getattr(message, "sender", None) if message is not None else None
    callback = getattr(event, "callback", None)
    for who in (getattr(callback, "user", None), sender, getattr(event, "user", None)):
        user_id = getattr(who, "user_id", None)
        if isinstance(user_id, int):
            return user_id
    return None

async def _from_deleted_account(session: AsyncSession, event: UpdateUnion) -> bool:
    from app.domain.account import account_key, lock_account

    user_id = _event_user_id(event)
    if user_id is None:
        return False
    await lock_account(session, user_id)
    stone = await session.get(AccountTombstone, account_key(user_id))
    if stone is None:
        return False
    sent_at = datetime.fromtimestamp(event.timestamp / 1000, tz=UTC)
    return sent_at <= stone.deleted_at

def _reason(error: BaseException) -> str:
    cause = getattr(error, "cause", None) or error.__cause__
    return type(cause or error).__name__

async def capture_error(event: ErrorEvent) -> None:
    _handler_error.set(event.exception)
