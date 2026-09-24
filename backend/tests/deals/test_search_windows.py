import uuid
from datetime import date, datetime, time, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deal_view import shift_point
from app.api.routers.search import pick_window, resolve_window
from app.db.enums import Category, OrgStatus, ShiftPlace, Transport
from app.db.models import BusySlot, FreeWindow, Schedule, Shift, User
from app.domain.search import Candidate, Origin, best_route, match, search
from app.domain.travel import Point, default_estimator
from app.domain.windows import Window, next_free_window, window_from_slots
from tests.conftest import NOW
from tests.deals.helpers import MSK, make_org, make_shift, msk
from tests.factories import make_user
from tests.support import dev

CAMPUS = Point(55.7904, 49.1208)
NOW_PARAMS = {"duration_min": 60, "when": "now", "from": "campus"}

class FixedEstimator:
    def __init__(self, minutes: int) -> None:
        self.value = minutes

    def minutes(self, a: Point, b: Point, transport: Transport) -> int:
        return self.value

def cand(key: int, start: datetime, minutes: int = 60, **kw: object) -> Candidate:
    defaults: dict[str, object] = {
        "category": Category.BOOKS,
        "point": CAMPUS,
        "district_id": "vakh",
        "online": False,
        "seats_left": 3,
    }
    defaults.update(kw)
    return Candidate(
        id=uuid.UUID(int=key),
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        **defaults,  # type: ignore[arg-type]
    )

async def busy_schedule(session: AsyncSession, user: User) -> None:
    session.add(Schedule(user_id=user.id, file_name="full.ics"))
    session.add(
        BusySlot(
            user_id=user.id,
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=5),
            title="Учёба",
        )
    )
    session.add(
        FreeWindow(
            user_id=user.id, starts_at=NOW + timedelta(hours=5), ends_at=NOW + timedelta(hours=7)
        )
    )
    await session.commit()

async def test_busy_schedule_has_no_window(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await busy_schedule(db_session, user)
    window, seats = await resolve_window(db_session, user, duration_min=60, when="now", now=NOW)
    assert window is None and seats == 1
    resolved = await pick_window(db_session, user, duration_min=60, when="now", now=NOW)
    assert resolved.source == "none"
    assert resolved.next_window == Window(NOW + timedelta(hours=5), NOW + timedelta(hours=7))
    longer = await pick_window(db_session, user, duration_min=180, when="now", now=NOW)
    assert longer.window is None and longer.next_window is None
    evening = await pick_window(db_session, user, duration_min=60, when="tonight", now=NOW)
    assert evening.source == "schedule"
    assert evening.window == Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 18, 30))

async def test_search_without_fitting_window_is_empty(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    await busy_schedule(db_session, user)
    org = await make_org(db_session)
    await make_shift(db_session, org, msk(2026, 9, 29, 12, 20), 30)

    data = (await client.get("/search", headers=dev(user), params=NOW_PARAMS)).json()
    assert data["window"] is None and data["windowSource"] == "none"
    assert data["items"] == [] and set(data["counts"].values()) == {0}
    nxt = data["nextWindow"]
    assert datetime.fromisoformat(nxt["from"]) == msk(2026, 9, 29, 17, 0)
    assert datetime.fromisoformat(nxt["to"]) == msk(2026, 9, 29, 19, 0)
    preview = await client.get("/search/preview", headers=dev(user), params=NOW_PARAMS)
    assert preview.json() == {"count": 0}

    other = await make_user(db_session)
    data = (await client.get("/search", headers=dev(other), params=NOW_PARAMS)).json()
    assert data["windowSource"] == "fallback" and data["nextWindow"] is None
    assert data["window"] is not None and len(data["items"]) == 1

async def test_search_excludes_study_with_travel(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    db_session.add(Schedule(user_id=user.id, file_name="a.ics"))
    db_session.add(
        BusySlot(
            user_id=user.id,
            starts_at=msk(2026, 9, 30, 19, 0),
            ends_at=msk(2026, 9, 30, 20, 30),
            title="Матан",
        )
    )
    await db_session.commit()
    org = await make_org(db_session)
    ok = await make_shift(db_session, org, msk(2026, 9, 30, 17, 0), 60)
    await make_shift(db_session, org, msk(2026, 9, 30, 18, 0), 55)
    params = {
        "duration_min": 180,
        "when": "tomorrow",
        "from": "campus",
        "window_from": "2026-09-30T16:30:00+03:00",
        "window_to": "2026-09-30T23:00:00+03:00",
    }
    data = (await client.get("/search", headers=dev(user), params=params)).json()
    assert data["windowSource"] == "explicit"
    assert [i["deal"]["id"] for i in data["items"]] == [str(ok.id)]

def test_match_excludes_study_both_ways() -> None:
    window = Window(msk(2026, 9, 29, 14, 0), msk(2026, 9, 29, 20, 0))
    origin = Origin(kind="campus", point=CAMPUS)
    study = [Window(msk(2026, 9, 29, 16, 0), msk(2026, 9, 29, 17, 0))]
    items = [
        cand(1, msk(2026, 9, 29, 14, 30), 75),
        cand(2, msk(2026, 9, 29, 14, 50), 60),
        cand(3, msk(2026, 9, 29, 15, 0), 55),
        cand(4, msk(2026, 9, 29, 17, 5), 30),
        cand(5, msk(2026, 9, 29, 17, 10), 30),
        cand(6, msk(2026, 9, 29, 16, 0), 30, online=True),
        cand(7, msk(2026, 9, 29, 16, 0), 30, booked_by_me=True),
    ]
    found = search(items, window, origin, Transport.WALK, FixedEstimator(10), study=study)
    assert [m.candidate.id.int for m in found] == [1, 2, 7, 5]
    plan = best_route(
        items[:3] + items[4:5], window, origin, Transport.WALK, FixedEstimator(10), study=study
    )
    assert plan is not None and plan.first.id.int in (1, 2) and plan.second.id.int == 5

def test_tonight_uses_evening_slot() -> None:
    morning = Window(NOW + timedelta(minutes=5), NOW + timedelta(hours=3))
    evening = Window(NOW + timedelta(hours=6), NOW + timedelta(hours=10))
    result = window_from_slots([morning, evening], "tonight", 60, NOW, MSK)
    assert result == Window(evening.starts_at, evening.starts_at + timedelta(hours=1))
    long = Window(msk(2026, 9, 29, 13, 0), msk(2026, 9, 29, 20, 0))
    assert window_from_slots([long], "tonight", 60, NOW, MSK) == Window(
        msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 18, 30)
    )
    later = msk(2026, 9, 29, 18, 2)
    assert window_from_slots([long], "tonight", 60, later, MSK) == Window(
        msk(2026, 9, 29, 18, 5), msk(2026, 9, 29, 19, 5)
    )
    short = Window(msk(2026, 9, 29, 13, 0), msk(2026, 9, 29, 18, 0))
    assert window_from_slots([short], "tonight", 60, NOW, MSK) is None
    assert window_from_slots([long], "tonight", 60, NOW, MSK, evening=time(19, 0)) == Window(
        msk(2026, 9, 29, 19, 0), msk(2026, 9, 29, 20, 0)
    )

def test_now_tomorrow_weekend_rules() -> None:
    now = msk(2026, 9, 29, 12, 0)
    soon = Window(msk(2026, 9, 29, 12, 10), msk(2026, 9, 29, 14, 0))
    later = Window(msk(2026, 9, 29, 12, 20), msk(2026, 9, 29, 14, 0))
    assert window_from_slots([soon], "now", 60, now, MSK) == Window(
        msk(2026, 9, 29, 12, 10), msk(2026, 9, 29, 13, 10)
    )
    assert window_from_slots([later], "now", 60, now, MSK) is None
    day = Window(msk(2026, 9, 30, 9, 0), msk(2026, 9, 30, 12, 0))
    eve = Window(msk(2026, 9, 30, 16, 0), msk(2026, 9, 30, 19, 0))
    assert window_from_slots([day, eve], "tomorrow", 60, now, MSK) == Window(
        msk(2026, 9, 30, 17, 30), msk(2026, 9, 30, 18, 30)
    )
    sat = Window(msk(2026, 10, 3, 8, 0), msk(2026, 10, 3, 13, 0))
    assert date(2026, 10, 3).weekday() == 5
    assert window_from_slots([sat], "weekend", 120, now, MSK) == Window(
        msk(2026, 10, 3, 11, 0), msk(2026, 10, 3, 13, 0)
    )
    assert next_free_window([day, eve, sat], 240, now) == Window(sat.starts_at, sat.ends_at)
    assert next_free_window([day], 240, now) is None

def test_unknown_location_is_not_zero_travel() -> None:
    window = Window(NOW, NOW + timedelta(hours=1))
    unknown = cand(1, NOW + timedelta(minutes=1), 58, point=None, district_id=None)
    campus = Origin("campus", point=CAMPUS)
    assert match(unknown, window, campus, Transport.WALK, default_estimator(), now=NOW) is None
    online = cand(2, NOW + timedelta(minutes=1), 58, point=None, online=True)
    assert match(online, window, campus, Transport.WALK, default_estimator(), now=NOW)
    home = Origin("home", home_district="vakh", districts=frozenset({"vakh"}))
    at_home = match(unknown, window, home, Transport.WALK, default_estimator(), now=NOW)
    assert at_home is None
    in_district = cand(3, NOW + timedelta(minutes=1), 58, point=None)
    found = match(in_district, window, home, Transport.WALK, default_estimator(), now=NOW)
    assert found is not None and found.travel_min is None and found.slack_min == 1
    other = cand(4, NOW + timedelta(minutes=5), 20)
    first = cand(5, NOW + timedelta(minutes=30), 20, point=None)
    assert best_route([other, first], window, campus, Transport.WALK, FixedEstimator(1)) is None

async def test_district_centroid_not_used_for_travel(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    org = await make_org(db_session)
    org.lat = org.lon = None
    await db_session.commit()
    shift = await make_shift(db_session, org, msk(2026, 9, 29, 18, 0), 60, district_id="vakh")
    assert shift_point(shift, org) is None
    deal = (await client.get(f"/deals/{shift.id}", headers=dev(user))).json()
    assert deal["travelMin"] is None
    params = {"duration_min": 120, "when": "tonight", "from": "campus"}
    data = (await client.get("/search", headers=dev(user), params=params)).json()
    assert data["items"] == []
    data = await client.get("/search", headers=dev(user), params={**params, "from": "home"})
    assert [i["deal"]["id"] for i in data.json()["items"]] == [str(shift.id)]

async def test_verify_sets_point_and_backfills_shifts(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operator = await make_user(db_session, is_operator=True)
    org = await make_org(db_session, "Новая", OrgStatus.PENDING)
    org.lat = org.lon = None
    org.district_id = None
    await db_session.commit()
    bare = await make_shift(db_session, org, msk(2026, 10, 1, 18, 0))
    own = await make_shift(db_session, org, msk(2026, 10, 1, 18, 0), lat=55.8, lon=49.2)
    online = await make_shift(db_session, org, msk(2026, 10, 1, 18, 0), place=ShiftPlace.ONLINE)
    url = f"/operator/orgs/{org.id}/verify"

    for bad in ({"lat": 10.0, "lon": 49.1}, {"lat": 55.79, "lon": 200.0}):
        r = await client.post(url, headers=dev(operator), json=bad)
        assert r.status_code == 422 and r.json() == {"code": "invalid_point"}
    r = await client.post(url, headers=dev(operator), json={"lat": 55.79})
    assert r.status_code == 422
    r = await client.post(
        url, headers=dev(operator), json={"lat": 55.79, "lon": 49.12, "districtId": "nope"}
    )
    assert r.status_code == 422 and r.json() == {"code": "unknown_district"}

    r = await client.post(
        url, headers=dev(operator), json={"lat": 55.79, "lon": 49.12, "districtId": "vakh"}
    )
    assert r.status_code == 200 and r.json()["status"] == "verified"
    assert r.json()["districtId"] == "vakh"
    await db_session.refresh(org)
    assert (org.lat, org.lon, org.district_id) == (55.79, 49.12, "vakh")
    points = {}
    for s in (bare, own, online):
        fresh = await db_session.get(Shift, s.id, populate_existing=True)
        assert fresh is not None
        points[s.id] = (fresh.lat, fresh.lon)
    assert points == {
        bare.id: (55.79, 49.12),
        own.id: (55.8, 49.2),
        online.id: (None, None),
    }
