import asyncio
import contextlib
import signal

import structlog

from app.bot import runtime as bot_runtime
from app.clock import current_time
from app.config import get_settings
from app.db import session as db
from app.log import configure_logging
from app.worker.jobs.sweeps import Sweeper
from app.worker.ops import Monitor
from app.worker.queue import run_once

log = structlog.get_logger("worker")

async def run_forever(stop: asyncio.Event) -> None:
    interval = get_settings().worker_poll_interval_seconds
    sweeper = Sweeper()
    monitor = Monitor()
    while not stop.is_set():
        await monitor.maybe_run(current_time())
        await sweeper.maybe_run(current_time())
        try:
            busy = await run_once(current_time())
        except Exception:
            log.exception("worker_poll_failed")
            busy = False
        if not busy:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)

async def main() -> None:
    configure_logging(get_settings().app_env)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker_started")
    try:
        await run_forever(stop)
    finally:
        await bot_runtime.shutdown()
        await db.dispose()
        log.info("worker_stopped")

if __name__ == "__main__":
    asyncio.run(main())
