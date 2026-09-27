from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import structlog
from maxapi import Bot, Dispatcher

from app.bot.transport import MaxapiTransport, MaxNotConfiguredError, MaxTransport, translate
from app.config import Settings, get_settings

log = structlog.get_logger("bot")

WEBHOOK_PATH = "/max/webhook"

@dataclass(slots=True)
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher
    transport: MaxTransport
    secret: str

_runtime: BotRuntime | None = None

def build_dispatcher() -> Dispatcher:
    from app.bot import updates
    from app.bot.handlers import build_router

    dispatcher = Dispatcher(router_id="vremya")
    dispatcher.include_routers(build_router())
    dispatcher.errors()(updates.capture_error)
    return dispatcher

def build_runtime(
    settings: Settings | None = None, transport: MaxTransport | None = None
) -> BotRuntime | None:
    settings = settings or get_settings()
    if not settings.max_bot_token:
        return None
    bot = Bot(token=settings.max_bot_token, auto_requests=False)
    if not settings.max_webhook_secret and settings.app_env == "prod":
        log.warning("bot_webhook_without_secret", effect="requests_rejected")
    return BotRuntime(
        bot=bot,
        dispatcher=build_dispatcher(),
        transport=transport or MaxapiTransport(bot),
        secret=settings.max_webhook_secret,
    )

def get_runtime() -> BotRuntime | None:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime

def set_runtime(runtime: BotRuntime | None) -> None:
    global _runtime
    _runtime = runtime

def get_transport() -> MaxTransport:
    runtime = get_runtime()
    if runtime is None:
        raise MaxNotConfiguredError()
    return runtime.transport

async def shutdown() -> None:
    global _runtime
    if _runtime is not None and isinstance(_runtime.transport, MaxapiTransport):
        await _runtime.transport.aclose()
    _runtime = None

async def set_webhook(url: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.max_bot_token:
        raise MaxNotConfiguredError()
    bot = Bot(token=settings.max_bot_token, auto_requests=False)
    try:
        current = await bot.get_subscriptions()
        for item in current.subscriptions:
            if item.url != url and urlsplit(item.url).path == urlsplit(url).path:
                await bot.unsubscribe_webhook(url=item.url)
        await bot.subscribe_webhook(url=url, secret=settings.max_webhook_secret or None)
    except Exception as exc:
        raise translate(exc) from exc
    finally:
        await bot.close_session()
