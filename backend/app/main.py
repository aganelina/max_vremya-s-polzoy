import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.errors import register_error_handlers
from app.api.router import ROOT_ROUTERS, build_api_router
from app.clock import current_time
from app.config import get_settings
from app.db import session as db
from app.log import configure_logging

log = structlog.get_logger("api")

BACKEND_DIR = Path(__file__).resolve().parent.parent

@lru_cache
def migration_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()

def _signing_check() -> str:
    from app.domain.participant_settings import participant_settings

    ps = participant_settings()
    for path in (ps.cert_sign_key_path, ps.cert_sign_cert_path):
        if path and not os.access(path, os.R_OK):
            return f"fail: {Path(path).name} unreadable"
    return "ok"

async def readiness(now: datetime) -> dict[str, str]:
    from app.worker.ops import HEARTBEAT_STALE_AFTER, last_beat

    checks: dict[str, str] = {}
    try:
        async with db.get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
            current = await session.scalar(text("SELECT version_num FROM alembic_version"))
            head = migration_head()
            checks["migrations"] = "ok" if current == head else f"fail: {current} != {head}"
            dictionaries = await session.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM universities) AND EXISTS(SELECT 1 FROM districts)"
                )
            )
            checks["dictionaries"] = "ok" if dictionaries else "fail: empty dictionaries"
            beat = await last_beat(session)
    except Exception as exc:
        log.warning("readiness_db_failed", reason=type(exc).__name__)
        checks.setdefault("database", f"fail: {type(exc).__name__}")
        checks.setdefault("migrations", "fail: database")
        beat = None
    checks["signing_key"] = _signing_check()
    if beat is None:
        checks["worker"] = "fail: no heartbeat"
    elif now - beat > HEARTBEAT_STALE_AFTER:
        checks["worker"] = f"fail: heartbeat {int((now - beat).total_seconds())} s ago"
    else:
        checks["worker"] = "ok"
    return checks

def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_env)
    app = FastAPI(
        title="Время с пользой",
        version="0.1.0",
        docs_url="/api/docs" if settings.dev_auth_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.dev_auth_enabled else None,
    )
    register_error_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        checks = await readiness(current_time())
        ready = all(value == "ok" for value in checks.values())
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status_code=200 if ready else 503,
        )

    app.include_router(build_api_router())
    for router in ROOT_ROUTERS:
        app.include_router(router)
    return app

def export_openapi(app: FastAPI) -> dict[str, object]:
    schema = dict(app.openapi())
    components = dict(schema.get("components", {}))
    components["securitySchemes"] = {
        "maxInitData": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Max-Init-Data",
            "description": "window.WebApp.initData мини-приложения MAX (подпись проверяется)",
        },
        "testAccount": {
            "type": "http",
            "scheme": "bearer",
            "description": "Тестовая учётная запись из TEST_ACCOUNTS (только для проверки)",
        },
    }
    schema["components"] = components
    schema["security"] = [{"maxInitData": []}, {"testAccount": []}]
    schema["servers"] = [{"url": "/"}]
    return schema

app = create_app()
