import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.db.models import DistrictAdjacency, HourLedger, User
from app.seed import seed_demo
from tests.conftest import NOW
from tests.support import dev


async def test_clean_pilot_has_dictionaries_without_demo(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    from sqlalchemy import delete

    from app.db.models import District, Org, University
    from app.seed import seed_by_mode

    async with db.transaction() as session:
        await session.execute(delete(DistrictAdjacency))
        await session.execute(delete(University))
        await session.execute(delete(District))
        assert await seed_by_mode(session, NOW, "false") == "skipped"
        assert await seed_by_mode(session, NOW, "false") == "skipped"
        assert await session.scalar(select(func.count()).select_from(User)) == 0
        assert await session.scalar(select(func.count()).select_from(Org)) == 0
    headers = dev(123456789)
    data = (await client.get("/dictionaries", headers=headers)).json()
    assert data["universities"] and data["districts"]
    assert (await client.post("/me/consent", headers=headers)).status_code == 200
    response = await client.post(
        "/me/onboarding",
        headers=headers,
        json={
            "universityId": data["universities"][0]["id"],
            "districtId": data["districts"][0]["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["onboarded"] is True

async def test_seed_demo_is_idempotent_and_serves_alina(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await client.get("/me", headers=dev(1))

    async def counts() -> tuple[int | None, int | None]:
        users = await db_session.scalar(select(func.count()).select_from(User))
        ledger = await db_session.scalar(select(func.count()).select_from(HourLedger))
        return users, ledger

    async with db.transaction() as session:
        await seed_demo(session, NOW)
    first = await counts()
    async with db.transaction() as session:
        await seed_demo(session, NOW)
    assert await counts() == first
    alina = await db_session.scalar(
        select(func.count()).select_from(User).where(User.max_user_id == 1)
    )
    assert alina == 1
    neighbors = await db_session.scalars(
        select(DistrictAdjacency.neighbor_id).where(DistrictAdjacency.district_id == "d2")
    )
    assert set(neighbors) == {"vakh", "d1"}

    me = (await client.get("/me", headers=dev(1))).json()
    assert me["firstName"] == "Алина"
    assert me["onboarded"] is True
    assert me["university"] == {"id": "kfu", "name": "КФУ"}
    assert me["district"] == {"id": "vakh", "name": "Вахитовский"}
    assert me["interests"] == ["people", "books"]
    assert me["transport"] == "walk" and me["notify"] == "all"
    assert me["roles"] == {"coordinator": True, "mentorEligible": True}
    assert me["stats"]["hoursYear"] == 4.5
    assert me["stats"]["deals"] >= 3

async def test_seed_mode_first_run_only_and_rolling_keeps_real_bookings(
    db_session: AsyncSession,
) -> None:
    from datetime import timedelta

    from app.db.models import Booking, Shift
    from app.seed import seed_by_mode
    from app.seed.ids import demo_id
    from tests.factories import make_user

    async with db.transaction() as session:
        assert await seed_by_mode(session, NOW, "false") == "skipped"
        assert await seed_by_mode(session, NOW, "true") == "seeded"
    async with db.transaction() as session:
        assert await seed_by_mode(session, NOW + timedelta(hours=1), "true") == "skipped"

    shifts = {key: await db_session.get(Shift, demo_id(key)) for key in ("r-yard", "r-homework")}
    before = {key: shift.starts_at for key, shift in shifts.items() if shift is not None}
    assert set(before) == {"r-yard", "r-homework"}
    real = await make_user(db_session)
    db_session.add(Booking(shift_id=demo_id("r-yard"), user_id=real.id))
    await db_session.commit()

    async with db.transaction() as session:
        assert await seed_by_mode(session, NOW + timedelta(days=1), "refresh") == "refreshed"
    db_session.expire_all()
    yard = await db_session.get(Shift, demo_id("r-yard"))
    homework = await db_session.get(Shift, demo_id("r-homework"))
    assert yard is not None and yard.starts_at == before["r-yard"]
    assert homework is not None and homework.starts_at != before["r-homework"]
