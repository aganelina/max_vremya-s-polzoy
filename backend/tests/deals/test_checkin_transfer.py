from datetime import timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import current_time
from app.db.enums import BookingStatus
from app.domain.checkin_code import current_code
from tests.deals.helpers import book, make_org, make_shift, msk
from tests.factories import make_user
from tests.support import dev


async def test_check_in_flow(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    org = await make_org(db_session)
    start = msk(2026, 9, 29, 18, 0)
    shift = await make_shift(db_session, org, start)
    booking = await book(db_session, shift, user)
    url = f"/bookings/{booking.id}/check-in"

    def at(moment):  # type: ignore[no-untyped-def]
        app.dependency_overrides[current_time] = lambda: moment
        return current_code(shift.checkin_secret, moment).code

    code = at(start - timedelta(minutes=20))
    assert (await client.post(url, headers=dev(user), json={"code": code})).json() == {
        "ok": False,
        "error": "too_early",
    }
    code = at(start - timedelta(minutes=5))
    resp = await client.post(url, headers=dev(user), json={"code": "123abc"})
    assert resp.json() == {"ok": False, "error": "wrong_code"}
    old = code
    at(start - timedelta(minutes=2))
    resp = await client.post(url, headers=dev(user), json={"code": old})
    assert resp.json() == {"ok": False, "error": "expired"}

    code = at(start + timedelta(minutes=12))
    resp = await client.post(url, headers=dev(user), json={"code": f"vremya:checkin:{code}"})
    data = resp.json()
    assert data["ok"] is True and data["late"] is True
    await db_session.refresh(booking)
    assert booking.status is BookingStatus.CHECKED_IN

    resp = await client.delete(url, headers=dev(user))
    assert resp.status_code == 204
    resp = await client.delete(url, headers=dev(user))
    assert resp.status_code == 409 and resp.json() == {"code": "not_checked_in"}

    code = at(start + timedelta(minutes=31))
    resp = await client.post(url, headers=dev(user), json={"code": code})
    assert resp.json() == {"ok": False, "error": "too_late"}

async def test_check_in_rate_limit_and_foreign(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    other = await make_user(db_session)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 29, 12, 5))
    booking = await book(db_session, shift, user)
    url = f"/bookings/{booking.id}/check-in"
    resp = await client.post(url, headers=dev(other), json={"code": "000000"})
    assert resp.status_code == 404
    for _ in range(5):
        await client.post(url, headers=dev(user), json={"code": "000000"})
    resp = await client.post(url, headers=dev(user), json={"code": "000000"})
    assert resp.status_code == 429 and resp.json() == {"code": "rate_limited"}

async def test_seat_transfer(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    timur = await make_user(db_session, first_name="Тимур")
    alina = await make_user(db_session, first_name="Алина")
    late = await make_user(db_session, first_name="Лейла")
    newbie = await make_user(db_session, onboarded=False)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), capacity=1)
    booking = await book(db_session, shift, timur)

    link = (await client.post(f"/bookings/{booking.id}/transfer", headers=dev(timur))).json()
    token = link["link"].split("tr_", 1)[1]
    view = (await client.get(f"/transfers/{token}", headers=dev(newbie))).json()
    assert view["status"] == "ok" and view["fromName"] == "Тимур"
    assert view["deal"]["id"] == str(shift.id)

    resp = await client.post(f"/transfers/{token}/claim", headers=dev(timur))
    assert resp.status_code == 409 and resp.json() == {"code": "own_transfer"}
    resp = await client.post(f"/transfers/{token}/claim", headers=dev(alina))
    assert resp.status_code == 200
    claimed = resp.json()
    assert claimed["dealId"] == str(shift.id) and claimed["status"] == "going"

    resp = await client.post(f"/transfers/{token}/claim", headers=dev(late))
    assert resp.status_code == 409 and resp.json() == {"code": "seat_taken"}
    view = (await client.get(f"/transfers/{token}", headers=dev(late))).json()
    assert view == {"status": "taken", "fromName": "Тимур", "deal": None}
    await db_session.refresh(booking)
    assert booking.status is BookingStatus.CANCELLED

    unknown = (await client.get("/transfers/nope", headers=dev(late))).json()
    assert unknown == {"status": "expired", "fromName": None, "deal": None}
