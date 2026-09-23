import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MAX_BOT_TOKEN", "123456:test-bot-token")

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.clock import current_time
from app.db import session as db_session_module
from app.db.base import Base
from app.db.models import *  # noqa: F403 — регистрирует все модели в Base.metadata
from app.main import create_app
from app.seed import base as seed_base

BACKEND_DIR = Path(__file__).resolve().parent.parent

_REFERENCE_TABLES = {"universities", "districts", "district_adjacency"}

NOW = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)

def _server_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_SERVER_URL", "postgresql+asyncpg://vremya:vremya@127.0.0.1:54330"
    )

async def _admin(server_url: str, sql: str) -> None:
    admin_engine = create_async_engine(f"{server_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text(sql))
    finally:
        await admin_engine.dispose()

def _run_migrations(database_url: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    server_url = _server_url()
    db_name = f"test_{uuid.uuid4().hex[:16]}"
    database_url = f"{server_url}/{db_name}"

    await _admin(server_url, f'CREATE DATABASE "{db_name}"')
    try:
        await asyncio.to_thread(_run_migrations, database_url)
        engine = create_async_engine(database_url, pool_pre_ping=True)
        db_session_module.configure(engine)
        async with db_session_module.transaction() as session:
            await seed_base.seed_dictionaries(session, NOW)
        try:
            yield engine
        finally:
            await db_session_module.dispose()
    finally:
        await _admin(server_url, f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')

@pytest_asyncio.fixture
async def clean_db(db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    names = [name for name in Base.metadata.tables if name not in _REFERENCE_TABLES]
    quoted = ", ".join(f'"{name}"' for name in names)
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))

@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine, clean_db: None) -> AsyncIterator[AsyncSession]:
    async with db_session_module.get_sessionmaker()() as session:
        yield session

@pytest.fixture
def app() -> Iterator[FastAPI]:
    application = create_app()
    application.dependency_overrides[current_time] = lambda: NOW
    yield application

@pytest_asyncio.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    from app.api.throttle import reset_all

    reset_all()
    yield
