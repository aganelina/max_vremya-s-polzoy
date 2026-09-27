from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.worker.queue import enqueue


def uuid_of(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, ValueError):
        return None

async def fan_out(
    session: AsyncSession, kind: str, payload: dict[str, Any], user_ids: list[uuid.UUID]
) -> None:
    for user_id in dict.fromkeys(user_ids):
        await enqueue(session, kind, {**payload, "user_id": str(user_id)})
