from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, OrgStatus, ShiftPlace, ShiftStatus
from app.db.models import Booking
from tests.deals.helpers import book, jobs, make_org, make_shift, msk
from tests.factories import make_user
from tests.support import dev

DEAL_KEYS = {
    "id",
    "title",
    "org",
    "category",
    "startsAt",
    "endsAt",
    "hours",
    "address",
    "addressNote",
    "description",
    "travelMin",
    "capacity",
    "quorum",
    "taken",
    "goingInitials",
    "checkInFrom",
    "checkInTo",
    "cancelUntil",
    "instructionsAt",
    "myBooking",
    "impact",
}
TONIGHT = {"duration_min": 120, "when": "tonight", "from": "campus"}

def iso(value: str) -> datetime:
    return datetime.fromisoformat(value)

async def test_search_fallback_window_counts_and_preview(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    other = await make_user(db_session, first_name="Дима")
    org = await make_org(db_session)
    fits = await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 60)
    await book(db_session, fits, other)
    tight = await make_shift(
        db_session, org, msk(2026, 9, 29, 17, 45), 30, category=Category.PEOPLE
    )
    await make_shift(db_session, org, msk(2026, 9, 29, 19, 0), 60)
    full = await make_shift(
        db_session, org, msk(2026, 9, 29, 18, 0), 30, capacity=1, title="Полная"
    )
    await book(db_session, full, other)
    pending = await make_org(db_session, "Непроверенная", OrgStatus.PENDING)
    await make_shift(db_session, pending, msk(2026, 9, 29, 18, 0), 30)
    await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 30, status=ShiftStatus.CANCELLED)

    resp = await client.get("/search", headers=dev(user), params=TONIGHT)
    assert resp.status_code == 200
    data = resp.json()
    assert iso(data["window"]["from"]) == msk(2026, 9, 29, 17, 30)
    assert iso(data["window"]["to"]) == msk(2026, 9, 29, 19, 30)
    ids = [i["deal"]["id"] for i in data["items"]]
    assert ids == [str(tight.id), str(fits.id)]
    first, second = data["items"]
    assert set(first["deal"]) == DEAL_KEYS
    assert first["deal"]["travelMin"] == 10
    assert first["slackMin"] == 5 and first["fit"] == "tight"
    assert second["slackMin"] == 20 and second["fit"] == "ok"
    assert second["deal"]["taken"] == 1 and second["deal"]["goingInitials"] == ["Д"]
    assert second["deal"]["hours"] == 1.0
    assert data["counts"] == {
        "all": 2,
        "near": 2,
        "people": 1,
        "animals": 0,
        "ecology": 0,
        "books": 1,
        "things": 0,
        "online": 0,
    }

    preview = await client.get("/search/preview", headers=dev(user), params=TONIGHT)
    assert preview.json() == {"count": 2}

async def test_search_home_and_explicit_window(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    org = await make_org(db_session)
    near = await make_shift(db_session, org, msk(2026, 9, 30, 10, 0), 60)
    far = await make_shift(db_session, org, msk(2026, 9, 30, 10, 0), 60, district_id="d5")
    online = await make_shift(
        db_session,
        org,
        msk(2026, 9, 30, 10, 30),
        30,
        place=ShiftPlace.ONLINE,
        category=Category.ONLINE,
        district_id="d5",
    )
    params = {
        "duration_min": 60,
        "when": "tomorrow",
        "from": "home",
        "window_from": "2026-09-30T09:30:00+03:00",
        "window_to": "2026-09-30T11:30:00+03:00",
    }
    data = (await client.get("/search", headers=dev(user), params=params)).json()
    items = {i["deal"]["id"]: i for i in data["items"]}
    assert set(items) == {str(near.id), str(online.id)}
    assert str(far.id) not in items
    assert items[str(near.id)]["deal"]["travelMin"] is None
    assert items[str(near.id)]["slackMin"] == 30
    assert items[str(online.id)]["deal"]["travelMin"] == 0

async def test_search_errors(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    bad = {**TONIGHT, "duration_min": 45}
    resp = await client.get("/search", headers=dev(user), params=bad)
    assert resp.status_code == 422 and resp.json() == {"code": "validation_error"}
    newbie = await make_user(db_session, onboarded=False)
    resp = await client.get("/search/preview", headers=dev(newbie), params=TONIGHT)
    assert resp.status_code == 403 and resp.json() == {"code": "onboarding_required"}

async def test_deal_detail(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), 90)
    shift.quorum = True
    await db_session.commit()
    resp = await client.get(f"/deals/{shift.id}", headers=dev(user))
    assert resp.status_code == 200
    deal = resp.json()
    assert set(deal) == DEAL_KEYS
    assert deal["quorum"] is True
    assert deal["org"] == {"id": str(org.id), "name": "Книжный мост", "verified": True}
    assert deal["hours"] == 1.5 and deal["addressNote"] == "вход со двора"
    assert iso(deal["cancelUntil"]) == msk(2026, 9, 30, 15, 0)
    assert iso(deal["checkInFrom"]) == msk(2026, 9, 30, 17, 45)
    assert iso(deal["checkInTo"]) == msk(2026, 9, 30, 18, 30)
    assert iso(deal["instructionsAt"]) == msk(2026, 9, 29, 19, 0)
    assert deal["myBooking"] is None

    resp = await client.get(f"/deals/{shift.id}", headers=dev(user), params={"from": "home"})
    assert resp.json()["travelMin"] is None
    for bad in ("nope", "00000000-0000-0000-0000-000000000000"):
        resp = await client.get(f"/deals/{bad}", headers=dev(user))
        assert resp.status_code == 404 and resp.json() == {"code": "deal_not_found"}

async def test_book_idempotent_and_instructions(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    org = await make_org(db_session)
    tomorrow = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0))
    today = await make_shift(db_session, org, msk(2026, 9, 29, 15, 0))

    resp = await client.post(f"/deals/{tomorrow.id}/bookings", headers=dev(user), json={})
    assert resp.status_code == 200
    booking = resp.json()
    assert booking["dealId"] == str(tomorrow.id) and booking["status"] == "going"
    assert booking["checkedInAt"] is None
    again = await client.post(f"/deals/{tomorrow.id}/bookings", headers=dev(user))
    assert again.json()["id"] == booking["id"]

    await client.post(f"/deals/{today.id}/bookings", headers=dev(user))
    queued = sorted(await jobs(db_session, "notify.instructions"), key=lambda j: j.run_at)
    assert len(queued) == 2
    assert queued[0].run_at == msk(2026, 9, 29, 12, 0)
    assert queued[1].run_at == msk(2026, 9, 29, 19, 0)
    assert queued[1].payload == {"booking_id": booking["id"]}

    deal = (await client.get(f"/deals/{tomorrow.id}", headers=dev(user))).json()
    assert deal["myBooking"]["id"] == booking["id"] and deal["taken"] == 1
    assert deal["goingInitials"] == []

async def test_book_seat_taken_and_time_conflict(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    other = await make_user(db_session)
    org = await make_org(db_session)
    full = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), capacity=1)
    await book(db_session, full, other)
    resp = await client.post(f"/deals/{full.id}/bookings", headers=dev(user))
    assert resp.status_code == 409 and resp.json() == {"code": "seat_taken"}

    a = await make_shift(db_session, org, msk(2026, 10, 1, 18, 0), 60)
    b = await make_shift(db_session, org, msk(2026, 10, 1, 18, 30), 60)
    assert (await client.post(f"/deals/{a.id}/bookings", headers=dev(user))).status_code == 200
    resp = await client.post(f"/deals/{b.id}/bookings", headers=dev(user))
    assert resp.status_code == 409 and resp.json() == {"code": "time_conflict"}

    past = await make_shift(db_session, org, msk(2026, 9, 29, 11, 0))
    resp = await client.post(f"/deals/{past.id}/bookings", headers=dev(user))
    assert resp.status_code == 409 and resp.json() == {"code": "deal_closed"}

async def test_cancel_booking(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    stranger = await make_user(db_session)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0))
    booking = (await client.post(f"/deals/{shift.id}/bookings", headers=dev(user))).json()

    resp = await client.delete(f"/bookings/{booking['id']}", headers=dev(stranger))
    assert resp.status_code == 404 and resp.json() == {"code": "booking_not_found"}
    assert (await client.delete(f"/bookings/{booking['id']}", headers=dev(user))).status_code == 204
    assert (await client.delete(f"/bookings/{booking['id']}", headers=dev(user))).status_code == 204
    deal = (await client.get(f"/deals/{shift.id}", headers=dev(user))).json()
    assert deal["myBooking"] is None and deal["taken"] == 0
    resp = await client.post(f"/deals/{shift.id}/bookings", headers=dev(user))
    assert resp.status_code == 200 and resp.json()["id"] != booking["id"]

async def test_friend_invite(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    alina = await make_user(db_session, first_name="Алина")
    friend = await make_user(db_session, onboarded=False)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), capacity=1)
    link = (await client.post(f"/deals/{shift.id}/invite", headers=dev(alina))).json()["link"]
    assert "?startapp=fr_" in link
    token = link.split("fr_", 1)[1]
    assert len(token) == 22
    again = (await client.post(f"/deals/{shift.id}/invite", headers=dev(alina))).json()["link"]
    assert again == link

    resp = await client.get(f"/invites/{token}", headers=dev(friend))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok" and data["inviterName"] == "Алина"
    assert data["deal"]["id"] == str(shift.id)

    await book(db_session, shift, alina)
    assert (await client.get(f"/invites/{token}", headers=dev(friend))).json()["status"] == "full"
    shift.status = ShiftStatus.CANCELLED
    await db_session.commit()
    resp = await client.get(f"/invites/{token}", headers=dev(friend))
    assert resp.json()["status"] == "expired"
    resp = await client.get("/invites/nope", headers=dev(friend))
    assert resp.status_code == 404 and resp.json() == {"code": "invite_not_found"}

async def test_book_via_invite(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    alina = await make_user(db_session)
    friend = await make_user(db_session)
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0))
    link = (await client.post(f"/deals/{shift.id}/invite", headers=dev(alina))).json()["link"]
    token = link.split("fr_", 1)[1]
    resp = await client.post(
        f"/deals/{shift.id}/bookings", headers=dev(friend), json={"inviteToken": token}
    )
    assert resp.status_code == 200
    booking = await db_session.get(Booking, resp.json()["id"])
    assert booking is not None and booking.via_invite_id is not None

async def test_deal_ics(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    shift = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), 90)
    resp = await client.get(f"/deals/{shift.id}/ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert "BEGIN:VEVENT" in body and "DTSTART:20260930T150000Z" in body
    assert "LOCATION:ул. Баумана\\, 19 (вход со двора)" in body
    assert "Спросить Гульнару" not in body.replace("\r\n ", "")
    today = await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 90)
    resp = await client.get(f"/deals/{today.id}/ics")
    assert "Спросить Гульнару" in resp.text.replace("\r\n ", "")
    resp = await client.get("/deals/00000000-0000-0000-0000-000000000000/ics")
    assert resp.status_code == 404
    pending = await make_org(db_session, "Заявка", OrgStatus.PENDING)
    hidden = await make_shift(db_session, pending, msk(2026, 9, 29, 18, 0), 90)
    resp = await client.get(f"/deals/{hidden.id}/ics")
    assert resp.status_code == 404

async def test_my_deals(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    from decimal import Decimal

    from app.db.enums import LedgerSource
    from app.db.models import HourLedger

    user = await make_user(db_session)
    org = await make_org(db_session)
    upcoming = await make_shift(db_session, org, msk(2026, 9, 30, 18, 0))
    later = await make_shift(db_session, org, msk(2026, 10, 2, 18, 0))
    past = await make_shift(db_session, org, msk(2026, 9, 20, 18, 0), title="Прошлое")
    await book(db_session, later, user)
    await book(db_session, upcoming, user)
    done = await book(db_session, past, user, BookingStatus.DONE)
    db_session.add(
        HourLedger(
            user_id=user.id,
            source=LedgerSource.SHIFT,
            ref_id=done.id,
            hours=Decimal("1.0"),
            org_id=org.id,
            accepted_at=msk(2026, 9, 20, 19, 0),
        )
    )
    await db_session.commit()

    data = (await client.get("/me/deals", headers=dev(user))).json()
    assert [d["id"] for d in data["upcoming"]] == [str(upcoming.id), str(later.id)]
    assert data["past"][0]["id"] == str(done.id)
    assert data["past"][0]["status"] == "done"
    assert data["past"][0]["canContact"] is True
    assert len(data["history"]) == 1
    item = data["history"][0]
    assert set(item) == {"id", "title", "date", "place", "hours"}
    assert item["title"] == "Прошлое" and item["place"] == "Книжный мост" and item["hours"] == 1.0
    _ = timedelta
