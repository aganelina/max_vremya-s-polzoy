from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Org
from app.seed import base
from app.seed import coord as coord_seed
from app.seed import deals as deals_seed
from app.seed import engagement as engagement_seed
from app.seed import rolling as rolling_seed
from app.seed.ids import demo_id

SeedStep = Callable[[AsyncSession, datetime], Awaitable[None]]

STEPS: list[SeedStep] = [
    base.seed_dictionaries,
    base.seed_orgs,
    base.seed_demo_user,
    base.seed_history,
    engagement_seed.seed_engagement,
    coord_seed.seed_coord,
    deals_seed.seed_deals,
    rolling_seed.seed_rolling,
]

async def seed_demo(session: AsyncSession, now: datetime) -> None:
    for step in STEPS:
        await step(session, now)

async def demo_present(session: AsyncSession) -> bool:
    return await session.get(Org, demo_id("o-books")) is not None

SEED_MODES = ("true", "refresh", "false")

async def seed_by_mode(session: AsyncSession, now: datetime, mode: str) -> str:
    mode = mode.strip().lower()
    if mode not in SEED_MODES:
        raise ValueError(f"SEED_DEMO: одно из {', '.join(SEED_MODES)}")
    await base.seed_dictionaries(session, now)
    if mode == "false":
        return "skipped"
    if mode == "true" and await demo_present(session):
        return "skipped"
    await seed_demo(session, now)
    return "refreshed" if mode == "refresh" else "seeded"
