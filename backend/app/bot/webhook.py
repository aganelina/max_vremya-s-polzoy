from __future__ import annotations

import hmac

import structlog
from fastapi import APIRouter, Request, Response
from maxapi.methods.types.getted_updates import process_update_webhook

from app.bot import updates
from app.bot.runtime import WEBHOOK_PATH, BotRuntime, get_runtime

log = structlog.get_logger("bot")

SECRET_HEADER = "X-Max-Bot-Api-Secret"  # noqa: S105 — имя заголовка, не секрет

router = APIRouter()

def secret_ok(runtime: BotRuntime, provided: str | None) -> bool:
    if not runtime.secret or provided is None:
        return False
    return hmac.compare_digest(provided.encode(), runtime.secret.encode())

@router.post(WEBHOOK_PATH, include_in_schema=False)
async def receive(request: Request) -> Response:
    runtime = get_runtime()
    if runtime is None:
        return Response(status_code=404)
    if not secret_ok(runtime, request.headers.get(SECRET_HEADER)):
        log.warning("max_webhook_bad_secret")
        return Response(status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)
    try:
        event = await process_update_webhook(event_json=payload, bot=runtime.bot)
    except Exception:
        log.warning("max_webhook_unparsed", update_type=str(payload.get("update_type")))
        return Response(status_code=200)
    if event is None:
        log.info("max_webhook_unknown_update", update_type=str(payload.get("update_type")))
        return Response(status_code=200)
    try:
        await updates.accept(event, payload)
    except Exception:
        log.exception("max_webhook_record_failed")
        return Response(status_code=503)
    return Response(status_code=200)
