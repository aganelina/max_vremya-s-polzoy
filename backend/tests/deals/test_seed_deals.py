import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.seed import seed_demo
from app.seed.deals import COMPANY_TOKEN, INVITE_TOKEN, TRANSFER_TOKEN
from app.seed.ids import demo_id
from tests.conftest import NOW
from tests.support import dev


async def test_seed_deals_match_mock(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    for _ in range(2):
        async with db.transaction() as session:
            await seed_demo(session, NOW)
    alina = dev(1)
    books = (await client.get(f"/deals/{demo_id('d-books')}", headers=alina)).json()
    assert books["title"] == "Разбор книг для сельских библиотек (демо)"
    assert books["myBooking"]["id"] == str(demo_id("b-books"))
    assert books["goingInitials"] == ["Д", "М", "К", "Т", "С"] and books["taken"] == 6
    assert books["hours"] == 1.5

    company = (await client.get(f"/companies/{demo_id('c-demo')}", headers=alina)).json()
    assert [m["firstName"] for m in company["members"]] == ["Алина", "Дима", "Лейла"]
    assert company["inviteLink"].endswith(f"co_{COMPANY_TOKEN}")
    assert company["pickedDealId"] == str(demo_id("d-books"))

    transfer = (await client.get(f"/transfers/{TRANSFER_TOKEN}", headers=alina)).json()
    assert transfer["status"] == "ok" and transfer["fromName"] == "Тимур"
    invite = (await client.get(f"/invites/{INVITE_TOKEN}", headers=alina)).json()
    assert invite["status"] == "ok" and invite["inviterName"] == "Дима"

    schedule = (await client.get("/me/schedule", headers=alina)).json()
    assert schedule["fileName"] is None
    assert [w["from"] for w in schedule["windows"]] == ["11:10", "14:40", "15:10"]

async def test_six_week_calendar_and_stable_seed_dates(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import timedelta

    from sqlalchemy import select

    from app.config import get_settings
    from app.db.models import Shift
    from app.seed.rolling import seed_rolling

    async with db.transaction() as session:
        await seed_demo(session, NOW)
    before = {s.id: s.starts_at for s in (await db_session.scalars(select(Shift))).all()}
    for day in range(1, 43):
        date = (NOW + timedelta(days=day)).astimezone(get_settings().tz).date().isoformat()
        starts = [before[demo_id(f"calendar-{date}-{slot}")] for slot in range(4)]
        assert len(set(starts)) == 4
        assert all(s.astimezone(get_settings().tz).date().isoformat() == date for s in starts)
        if day != 1 and day % 7 != 0:
            continue
        response = await client.get("/events", params={"date": date}, headers=dev(1))
        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 4
        assert len({e["startsAt"] for e in events}) >= 4
        assert all(e["startsAt"].startswith(date) for e in events)
    async with db.transaction() as session:
        await seed_rolling(session, NOW)
        await seed_rolling(session, NOW + timedelta(days=1), calendar_only=True)
    db_session.expunge_all()
    dated_id = demo_id(f"calendar-{(NOW + timedelta(days=7)).date()}-0")
    shift = await db_session.get(Shift, dated_id)
    assert shift.starts_at == before[dated_id]
    for existing in (await db_session.scalars(select(Shift))).all():
        if existing.id in before:
            assert existing.starts_at == before[existing.id]
    assert (
        await client.get("/events", params={"date": "nonsense"}, headers=dev(1))
    ).status_code == 422
