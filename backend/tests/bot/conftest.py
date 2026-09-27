from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from maxapi import Bot
from maxapi.methods.types.getted_updates import process_update_webhook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import runtime as bot_runtime
from app.bot import updates
from app.bot.runtime import BotRuntime, build_dispatcher
from app.bot.transport import FakeMaxTransport
from app.db import session as db
from app.db.enums import Category
from app.db.models import Job, MaxChat, Org, Shift, User
from app.worker.queue import run_once
from tests.support import BOT_TOKEN

WEBHOOK_SECRET = "webhook-secret-1234"

@dataclass(frozen=True)
class Outcome:
    duplicate: bool = False
    failed: bool = False

@dataclass
class BotHarness:
    runtime: BotRuntime
    transport: FakeMaxTransport

    async def deliver(self, event_json: dict[str, Any]) -> Outcome:
        event = await process_update_webhook(event_json=event_json, bot=self.runtime.bot)
        assert event is not None, "событие не распознано библиотекой"
        if not await updates.accept(event, event_json):
            return Outcome(duplicate=True)
        return Outcome(failed=not await run_bot_updates())

async def run_bot_updates(at: datetime | None = None) -> bool:
    moment = at or now() + timedelta(seconds=1)
    while await run_once(moment, kinds={updates.JOB_KIND}):
        pass
    async with db.transaction() as session:
        left = await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == updates.JOB_KIND, Job.done_at.is_(None))
        )
    return left == 0

@pytest.fixture
def harness(clean_db: None) -> Iterator[BotHarness]:
    transport = FakeMaxTransport()
    runtime = BotRuntime(
        bot=Bot(token=BOT_TOKEN, auto_requests=False),
        dispatcher=build_dispatcher(),
        transport=transport,
        secret=WEBHOOK_SECRET,
    )
    bot_runtime.set_runtime(runtime)
    try:
        yield BotHarness(runtime, transport)
    finally:
        bot_runtime.set_runtime(None)

def now() -> datetime:
    return datetime.now(UTC)

async def drain(limit: int = 100) -> int:
    done = 0
    while done < limit and await run_once(now() + timedelta(seconds=1)):
        done += 1
    return done

_mids = count(1)
_callbacks = count(1)
_ts = count(1_700_000_000_000)

def max_user(user_id: int, name: str = "Алина") -> dict[str, Any]:
    return {"user_id": user_id, "first_name": name, "is_bot": False, "last_activity_time": 1}

def message_created(
    text: str,
    *,
    user_id: int,
    chat_id: int,
    mid: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    ts = next(_ts)
    message: dict[str, Any] = {
        "sender": max_user(user_id),
        "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
        "timestamp": ts,
        "body": {"mid": mid or f"in-mid-{next(_mids)}", "seq": 1, "text": text},
    }
    if reply_to is not None:
        message["link"] = {
            "type": "reply",
            "chat_id": chat_id,
            "message": {"mid": reply_to, "seq": 1, "text": ""},
        }
    return {"update_type": "message_created", "timestamp": ts, "message": message}

def bot_started(*, user_id: int, chat_id: int, payload: str | None = None) -> dict[str, Any]:
    return {
        "update_type": "bot_started",
        "timestamp": next(_ts),
        "chat_id": chat_id,
        "user": max_user(user_id),
        "payload": payload,
    }

def message_callback(payload: str, *, user_id: int, chat_id: int) -> dict[str, Any]:
    ts = next(_ts)
    return {
        "update_type": "message_callback",
        "timestamp": ts,
        "callback": {
            "timestamp": ts,
            "callback_id": f"cb-{next(_callbacks)}",
            "payload": payload,
            "user": max_user(user_id),
        },
        "message": {
            "sender": max_user(user_id),
            "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
            "timestamp": ts,
            "body": {"mid": f"cb-mid-{next(_mids)}", "seq": 1, "text": "вызов"},
        },
    }

async def with_chat(session: AsyncSession, user: User) -> int:
    chat_id = user.max_user_id + 100_000
    session.add(MaxChat(user_id=user.id, chat_id=chat_id))
    await session.commit()
    return chat_id

async def make_shift(
    session: AsyncSession,
    org: Org,
    *,
    starts_at: datetime | None = None,
    minutes: int = 90,
    capacity: int = 5,
    title: str = "Разбор книг",
) -> Shift:
    starts = starts_at or now() + timedelta(days=1)
    shift = Shift(
        org_id=org.id,
        title=title,
        category=Category.BOOKS,
        starts_at=starts,
        ends_at=starts + timedelta(minutes=minutes),
        capacity=capacity,
        address="ул. Баумана, 1",
        instructions="Возьми перчатки",
        checkin_secret=os.urandom(20),
    )
    session.add(shift)
    await session.commit()
    return shift
