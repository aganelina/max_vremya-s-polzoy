from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Booking
from tests.deals.helpers import book, jobs, make_org, make_shift, msk
from tests.factories import make_user
from tests.support import dev

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:a
DTSTART;TZID=Europe/Moscow:20260929T093000
DTEND;TZID=Europe/Moscow:20260929T110000
RRULE:FREQ=WEEKLY;COUNT=4
SUMMARY:История
END:VEVENT
BEGIN:VEVENT
UID:b
DTSTART;TZID=Europe/Moscow:20260929T133000
DTEND;TZID=Europe/Moscow:20260929T150000
SUMMARY:Матан
END:VEVENT
END:VCALENDAR
"""

async def test_schedule_upload_and_window(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    empty = (await client.get("/me/schedule", headers=dev(user))).json()
    assert empty == {"fileName": None, "windows": []}

    files = {"file": ("raspisanie.ics", ICS.encode(), "text/calendar")}
    resp = await client.post("/me/schedule", headers=dev(user), files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["fileName"] == "raspisanie.ics"
    first = data["windows"][0]
    assert set(first) == {"id", "day", "from", "to", "startsAt", "endsAt", "after", "place"}
    assert (first["day"], first["from"], first["to"], first["after"], first["place"]) == (
        "Вторник",
        "11:00",
        "13:30",
        "после «История»",
        "КФУ, главный",
    )
    assert [w["from"] for w in data["windows"]] == ["11:00", "15:00"]

    res = (
        await client.get(
            "/search",
            headers=dev(user),
            params={"duration_min": 120, "when": "tonight", "from": "campus"},
        )
    ).json()
    assert res["windowSource"] == "schedule"
    assert datetime.fromisoformat(res["window"]["from"]) == msk(2026, 9, 29, 17, 30)

    bad = {"file": ("x.ics", b"not a calendar", "text/calendar")}
    resp = await client.post("/me/schedule", headers=dev(user), files=bad)
    assert resp.status_code == 422 and resp.json() == {"code": "ics_invalid"}

async def test_company_flow(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    alina = await make_user(db_session, first_name="Алина")
    dima = await make_user(db_session, first_name="Дима")
    leila = await make_user(db_session, first_name="Лейла")
    stranger = await make_user(db_session)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 60)

    company = (
        await client.post("/companies", headers=dev(alina), json={"date": "2026-09-29"})
    ).json()
    cid = company["id"]
    token = company["inviteLink"].split("co_", 1)[1]
    assert company["members"][0]["isMe"] is True and company["commonWindow"] is None
    for u in (dima, leila):
        resp = await client.post(f"/companies/join/{token}", headers=dev(u))
        assert resp.status_code == 200
    windows = {
        alina: ("2026-09-29T17:00:00+03:00", "2026-09-29T19:40:00+03:00"),
        dima: ("2026-09-29T17:30:00+03:00", "2026-09-29T21:00:00+03:00"),
    }
    for u, (f, t) in windows.items():
        await client.put(
            f"/companies/{cid}/window", headers=dev(u), json={"window": {"from": f, "to": t}}
        )
    data = (await client.get(f"/companies/{cid}", headers=dev(alina))).json()
    assert set(data) == {
        "id",
        "date",
        "commonWindow",
        "members",
        "inviteLink",
        "deals",
        "pickedDealId",
    }
    assert datetime.fromisoformat(data["commonWindow"]["from"]) == msk(2026, 9, 29, 17, 30)
    assert datetime.fromisoformat(data["commonWindow"]["to"]) == msk(2026, 9, 29, 19, 40)
    assert [m["firstName"] for m in data["members"]] == ["Алина", "Дима", "Лейла"]
    assert [d["deal"]["id"] for d in data["deals"]] == [str(shift.id)]

    for u in (alina, dima):
        resp = await client.post(
            f"/deals/{shift.id}/bookings", headers=dev(u), json={"companyId": cid}
        )
        assert resp.status_code == 200
    picked = (
        await client.put(
            f"/companies/{cid}/pick", headers=dev(alina), json={"dealId": str(shift.id)}
        )
    ).json()
    assert picked["pickedDealId"] == str(shift.id)
    assert picked["deals"][0]["votes"] == ["Ты", "Дима"]

    leila_id = str(leila.id)
    resp = await client.post(f"/companies/{cid}/members/{leila_id}/remind", headers=dev(alina))
    assert resp.status_code == 204
    queued = await jobs(db_session, "notify.company_remind")
    assert queued[0].payload == {"company_id": cid, "member_user_id": leila_id}
    data = (await client.get(f"/companies/{cid}", headers=dev(alina))).json()
    assert data["members"][2]["remindedAt"] is not None

    resp = await client.post(f"/companies/{cid}/members/{alina.id}/remind", headers=dev(alina))
    assert resp.status_code == 409 and resp.json() == {"code": "cannot_remind_self"}
    resp = await client.get(f"/companies/{cid}", headers=dev(stranger))
    assert resp.status_code == 404 and resp.json() == {"code": "company_not_found"}

async def test_route_and_atomic_booking(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    other = await make_user(db_session)
    org = await make_org(db_session)
    a = await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 40)
    b = await make_shift(db_session, org, msk(2026, 9, 29, 19, 0), 60, capacity=1)

    route = (await client.get("/route", headers=dev(user))).json()
    assert set(route) == {"window", "legs"}
    assert [leg["deal"]["id"] for leg in route["legs"]] == [str(a.id), str(b.id)]
    assert route["legs"][0]["walkToNextMin"] == 3 and route["legs"][1]["walkToNextMin"] is None

    await book(db_session, b, other)
    resp = await client.post(
        "/route/bookings", headers=dev(user), json={"dealIds": [str(a.id), str(b.id)]}
    )
    assert resp.status_code == 409 and resp.json() == {"code": "seat_taken"}
    mine = await db_session.scalars(select(Booking).where(Booking.user_id == user.id))
    assert mine.all() == []

    c = await make_shift(db_session, org, msk(2026, 9, 29, 19, 0), 60)
    resp = await client.post(
        "/route/bookings", headers=dev(user), json={"dealIds": [str(a.id), str(c.id)]}
    )
    assert resp.status_code == 204
    mine = await db_session.scalars(select(Booking).where(Booking.user_id == user.id))
    assert len(mine.all()) == 2

    lonely = await make_user(db_session)
    await db_session.commit()
    resp = await client.get("/route", headers=dev(lonely), params={"when": "weekend"})
    assert resp.status_code == 404 and resp.json() == {"code": "no_route"}
