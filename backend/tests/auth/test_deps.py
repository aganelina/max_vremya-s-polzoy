from datetime import timedelta

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import deps
from app.auth.deps import Coordinator, OnboardedUser, Operator
from app.config import Settings
from app.db.enums import OrgRole, OrgStatus
from app.db.models import User
from tests.conftest import NOW
from tests.factories import add_member, make_org, make_user
from tests.support import dev, sign_init_data


async def test_init_data_creates_user_and_refreshes_first_name(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    raw = sign_init_data({"id": 777, "first_name": "Ира", "last_name": "Секретова"}, NOW)
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.status_code == 200
    assert resp.json()["firstName"] == "Ира"
    assert resp.json()["onboarded"] is False

    raw = sign_init_data({"id": 777, "first_name": "Ирина"}, NOW)
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.json()["firstName"] == "Ирина"

    users = (await db_session.scalars(select(User).where(User.max_user_id == 777))).all()
    assert [u.first_name for u in users] == ["Ирина"]

async def test_bad_signature(client: httpx.AsyncClient) -> None:
    raw = sign_init_data({"id": 1, "first_name": "Х"}, NOW, token="чужой-токен")
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.status_code == 401
    assert resp.json() == {"code": "init_data_invalid"}

async def test_expired(client: httpx.AsyncClient) -> None:
    raw = sign_init_data({"id": 1, "first_name": "Х"}, NOW - timedelta(hours=25))
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.status_code == 401
    assert resp.json() == {"code": "init_data_expired"}

async def test_day_old_init_data_is_accepted(client: httpx.AsyncClient) -> None:
    raw = sign_init_data({"id": 1, "first_name": "Х"}, NOW - timedelta(hours=23))
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.status_code == 200

async def test_no_credentials(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me")
    assert resp.status_code == 401
    assert resp.json() == {"code": "init_data_invalid"}

async def test_dev_user_bad_value(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me", headers={"X-Dev-User": "alina"})
    assert resp.status_code == 401

@pytest.mark.parametrize("env", ["prod"])
async def test_dev_user_ignored_outside_dev(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    settings = Settings(
        app_env=env,  # type: ignore[arg-type]
        max_bot_token="x",
        max_webhook_secret="hook-secret",
        public_base_url="https://vremya.example.ru",
    )
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    resp = await client.get("/me", headers=dev(1))
    assert resp.status_code == 401
    assert resp.json() == {"code": "init_data_invalid"}

async def test_init_data_rejected_without_bot_token(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(app_env="test", max_bot_token="")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    raw = sign_init_data({"id": 1, "first_name": "Х"}, NOW, token="")
    resp = await client.get("/me", headers={"X-Max-Init-Data": raw})
    assert resp.status_code == 401

@pytest.fixture
def guarded_app(app: FastAPI) -> FastAPI:
    router = APIRouter(prefix="/api/v1/_t")

    @router.get("/onboarded")
    async def onboarded(user: OnboardedUser) -> dict[str, str]:
        return {"id": str(user.id)}

    @router.get("/coord")
    async def coord(ctx: Coordinator) -> dict[str, str]:
        return {"org": str(ctx.org.id), "role": ctx.role.value}

    @router.get("/operator")
    async def operator(user: Operator) -> dict[str, str]:
        return {"id": str(user.id)}

    app.include_router(router)
    return app

@pytest.fixture
async def gclient(guarded_app: FastAPI, client: httpx.AsyncClient) -> httpx.AsyncClient:
    return client

async def test_onboarding_gate(gclient: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, onboarded=False)
    headers = dev(user)
    for method, path, body in [
        ("GET", "/_t/onboarded", None),
        ("PATCH", "/me", {"transport": "scooter"}),
        ("PUT", "/me/weekly-search", {"params": None}),
    ]:
        resp = await gclient.request(method, path, headers=headers, json=body)
        assert resp.status_code == 403, path
        assert resp.json() == {"code": "onboarding_required"}

    assert (await gclient.get("/me", headers=headers)).status_code == 200
    assert (await gclient.get("/dictionaries", headers=headers)).status_code == 200

    assert (await gclient.post("/me/consent", headers=headers)).status_code == 200
    resp = await gclient.get("/_t/onboarded", headers=headers)
    assert resp.json() == {"code": "onboarding_required"}

    resp = await gclient.post(
        "/me/onboarding", headers=headers, json={"universityId": "u2", "districtId": "d3"}
    )
    assert resp.status_code == 200
    assert (await gclient.get("/_t/onboarded", headers=headers)).status_code == 200

async def test_coordinator_requires_verified_active_membership(
    gclient: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    resp = await gclient.get("/_t/coord", headers=dev(user))
    assert resp.status_code == 403
    assert resp.json() == {"code": "not_coordinator"}

    pending = await make_org(db_session, status=OrgStatus.PENDING)
    await add_member(db_session, pending, user, role=OrgRole.OWNER)
    assert (await gclient.get("/_t/coord", headers=dev(user))).status_code == 403

    revoked_org = await make_org(db_session)
    await add_member(db_session, revoked_org, user, revoked_at=NOW)
    assert (await gclient.get("/_t/coord", headers=dev(user))).status_code == 403

    org = await make_org(db_session)
    await add_member(db_session, org, user, role=OrgRole.COORDINATOR)
    resp = await gclient.get("/_t/coord", headers=dev(user))
    assert resp.status_code == 200
    assert resp.json() == {"org": str(org.id), "role": "coordinator"}
    assert (await gclient.get("/me", headers=dev(user))).json()["roles"]["coordinator"] is True

async def test_coordinator_passes_onboarding_gate_first(
    gclient: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, onboarded=False)
    org = await make_org(db_session)
    await add_member(db_session, org, user)
    resp = await gclient.get("/_t/coord", headers=dev(user))
    assert resp.json() == {"code": "onboarding_required"}

async def test_operator(gclient: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    resp = await gclient.get("/_t/operator", headers=dev(user))
    assert resp.status_code == 403
    assert resp.json() == {"code": "not_operator"}

    operator = await make_user(db_session, is_operator=True)
    assert (await gclient.get("/_t/operator", headers=dev(operator))).status_code == 200
