from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import current_time
from app.db.enums import LedgerSource
from tests.conftest import NOW
from tests.factories import credit, done_booking, make_org, make_user
from tests.support import dev

ME_KEYS = {
    "id",
    "firstName",
    "onboarded",
    "consentAt",
    "university",
    "district",
    "interests",
    "transport",
    "notify",
    "pauseUntil",
    "weeklySearch",
    "stats",
    "roles",
}
STATS_KEYS = {"hoursYear", "hoursMonth", "deals", "streakWeeks", "bankBalance"}
ROLES_KEYS = {"coordinator", "mentorEligible"}

def msk(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC) - timedelta(hours=3)  # type: ignore[misc]

async def test_new_user_me_shape(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me", headers=dev(5001))
    assert resp.status_code == 200
    me = resp.json()
    assert set(me) == ME_KEYS
    assert set(me["stats"]) == STATS_KEYS
    assert set(me["roles"]) == ROLES_KEYS
    assert me["onboarded"] is False
    assert me["consentAt"] is None
    assert me["university"] is None and me["district"] is None
    assert me["interests"] == []
    assert me["transport"] == "walk"
    assert me["notify"] == "all"
    assert me["pauseUntil"] is None and me["weeklySearch"] is None
    assert me["stats"] == {
        "hoursYear": 0,
        "hoursMonth": 0,
        "deals": 0,
        "streakWeeks": 0,
        "bankBalance": 0,
    }
    assert me["roles"] == {"coordinator": False, "mentorEligible": False}

async def test_stats_from_ledger(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    app.dependency_overrides[current_time] = lambda: msk(2026, 10, 6, 12, 0)
    user = await make_user(db_session)
    await credit(db_session, user, "1.0", msk(2026, 8, 31, 23, 30))
    await credit(db_session, user, "2.0", msk(2026, 9, 1, 0, 30), LedgerSource.MICRO)
    await credit(db_session, user, "1.5", msk(2026, 9, 22, 18, 0))
    await credit(db_session, user, "0.5", msk(2026, 9, 29, 18, 0))
    await credit(db_session, user, "1.0", msk(2026, 10, 5, 12, 0))
    await credit(db_session, user, "3.0", msk(2026, 9, 20, 12, 0), LedgerSource.BANK_HELP)
    await credit(db_session, user, "-1.0", msk(2026, 9, 21, 12, 0), LedgerSource.BANK_SPEND)
    org = await make_org(db_session)
    await done_booking(db_session, org, user, msk(2026, 9, 22, 17, 0))
    await done_booking(db_session, org, user, msk(2026, 9, 29, 17, 0))

    me = (await client.get("/me", headers=dev(user))).json()
    assert me["stats"] == {
        "hoursYear": 5.0,
        "hoursMonth": 1.0,
        "deals": 2,
        "streakWeeks": 3,
        "bankBalance": 8.0,
    }
    assert me["roles"]["mentorEligible"] is False

    await done_booking(db_session, org, user, msk(2026, 10, 5, 17, 0))
    me = (await client.get("/me", headers=dev(user))).json()
    assert me["roles"]["mentorEligible"] is True

async def test_bank_spend_sign_is_normalized(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    await credit(db_session, user, "2.0", NOW - timedelta(days=1))
    await credit(db_session, user, "0.5", NOW - timedelta(days=1), LedgerSource.BANK_SPEND)
    me = (await client.get("/me", headers=dev(user))).json()
    assert me["stats"]["bankBalance"] == 1.5

async def test_consent_is_recorded_once(client: httpx.AsyncClient) -> None:
    first = (await client.post("/me/consent", headers=dev(5002))).json()
    assert first["consentAt"] is not None
    assert datetime.fromisoformat(first["consentAt"]) == NOW
    again = (await client.post("/me/consent", headers=dev(5002))).json()
    assert again["consentAt"] == first["consentAt"]

async def test_onboarding(client: httpx.AsyncClient) -> None:
    headers = dev(5003)
    resp = await client.post(
        "/me/onboarding", headers=headers, json={"universityId": "kfu", "districtId": "vakh"}
    )
    assert resp.status_code == 403
    assert resp.json() == {"code": "consent_required"}

    await client.post("/me/consent", headers=headers)
    resp = await client.post(
        "/me/onboarding", headers=headers, json={"universityId": "nope", "districtId": "vakh"}
    )
    assert resp.status_code == 422
    assert resp.json() == {"code": "unknown_university"}

    resp = await client.post(
        "/me/onboarding", headers=headers, json={"universityId": "u3", "districtId": "d5"}
    )
    assert resp.status_code == 200
    me = resp.json()
    assert me["onboarded"] is True
    assert me["university"] == {"id": "u3", "name": "КГМУ"}
    assert me["district"] == {"id": "d5", "name": "Кировский"}

async def test_patch_profile(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    headers = dev(user)
    resp = await client.patch(
        "/me",
        headers=headers,
        json={
            "interests": ["animals", "online", "animals"],
            "transport": "scooter",
            "notify": "pause",
            "universityId": "u4",
            "districtId": "d6",
        },
    )
    assert resp.status_code == 200
    me = resp.json()
    assert me["interests"] == ["animals", "online"]
    assert me["transport"] == "scooter"
    assert me["notify"] == "pause"
    assert datetime.fromisoformat(me["pauseUntil"]) == NOW + timedelta(days=7)
    assert me["university"]["id"] == "u4"
    assert me["district"] == {"id": "d6", "name": "Авиастроительный"}

    me = (await client.patch("/me", headers=headers, json={"notify": "mine"})).json()
    assert me["notify"] == "mine"
    assert me["pauseUntil"] is None
    assert me["transport"] == "scooter"
    assert me["interests"] == ["animals", "online"]

@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"interests": ["cats"]}, "validation_error"),
        ({"transport": "car"}, "validation_error"),
        ({"notify": "never"}, "validation_error"),
        ({"districtId": "nowhere"}, "unknown_district"),
    ],
)
async def test_patch_profile_rejects_invalid(
    client: httpx.AsyncClient, db_session: AsyncSession, body: dict[str, object], code: str
) -> None:
    user = await make_user(db_session)
    resp = await client.patch("/me", headers=dev(user), json=body)
    assert resp.status_code == 422
    assert resp.json() == {"code": code}

async def test_weekly_search(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    headers = dev(user)
    params = {
        "durationMin": 60,
        "when": "tonight",
        "from": "campus",
        "window": {"from": "2026-09-29T17:30:00+03:00", "to": "2026-09-29T19:30:00+03:00"},
    }
    resp = await client.put("/me/weekly-search", headers=headers, json={"params": params})
    assert resp.status_code == 204
    saved = (await client.get("/me", headers=headers)).json()["weeklySearch"]
    assert saved["durationMin"] == 60 and saved["when"] == "tonight" and saved["from"] == "campus"
    assert "companyId" not in saved
    assert datetime.fromisoformat(saved["window"]["from"]) == datetime.fromisoformat(
        params["window"]["from"]  # type: ignore[index]
    )

    params = {"durationMin": 180, "when": "weekend", "from": "home"}
    await client.put("/me/weekly-search", headers=headers, json={"params": params})
    assert (await client.get("/me", headers=headers)).json()["weeklySearch"] == params

    await client.put("/me/weekly-search", headers=headers, json={"params": None})
    assert (await client.get("/me", headers=headers)).json()["weeklySearch"] is None

    bad = {"params": {"durationMin": 45, "when": "now", "from": "campus"}}
    resp = await client.put("/me/weekly-search", headers=headers, json=bad)
    assert resp.status_code == 422
    assert resp.json() == {"code": "validation_error"}

async def test_dictionaries(client: httpx.AsyncClient) -> None:
    assert (await client.get("/dictionaries")).status_code == 401
    resp = await client.get("/dictionaries", headers=dev(5004))
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"universities", "districts"}
    assert data["universities"] == [
        {"id": "kfu", "name": "КФУ"},
        {"id": "u1", "name": "КНИТУ"},
        {"id": "u2", "name": "КАИ"},
        {"id": "u3", "name": "КГМУ"},
        {"id": "u4", "name": "КГЭУ"},
        {"id": "u5", "name": "КГАСУ"},
        {"id": "u6", "name": "Другой"},
    ]
    assert [d["id"] for d in data["districts"]] == ["vakh", "d1", "d2", "d3", "d4", "d5", "d6"]
    assert data["districts"][0] == {"id": "vakh", "name": "Вахитовский"}

async def test_unknown_route_error_shape(client: httpx.AsyncClient) -> None:
    resp = await client.get("/no-such-route", headers=dev(5005))
    assert resp.status_code == 404
    assert resp.json() == {"code": "not_found"}
