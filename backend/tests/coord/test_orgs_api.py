import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrgRole, OrgStatus
from app.db.models import Job, Org, OrgMember
from app.domain.orgs import PNG_MAGIC
from tests.coord.conftest import Team
from tests.factories import make_org, make_user
from tests.support import dev

FORM = {
    "name": "Добрые соседи",
    "inn": "1655000000",
    "address": "ул. Баумана, 1",
    "districtId": "vakh",
    "contactName": "Ольга",
    "contactPhone": "+7 900 123-45-67",
    "signName": "О. П. Иванова",
    "signPosition": "директор",
}

async def test_apply_org_with_images(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    png = PNG_MAGIC + b"data"
    r = await client.post(
        "/orgs",
        data=FORM,
        files={"seal": ("seal.png", png, "image/png")},
        headers=dev(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending" and body["role"] == "owner"
    assert body["hasSeal"] is True and body["hasSignature"] is False
    org = await db_session.get(Org, body["id"])
    assert org is not None and org.seal_image == png and org.created_by == user.id
    member = await db_session.get(OrgMember, (org.id, user.id))
    assert member is not None and member.role is OrgRole.OWNER

    r = await client.get("/orgs/mine", headers=dev(user))
    assert [o["id"] for o in r.json()] == [body["id"]]

    r = await client.post("/orgs", data=FORM, headers=dev(user))
    assert r.status_code == 409 and r.json()["code"] == "application_pending"

    r = await client.get("/coord/home", headers=dev(user))
    assert r.status_code == 403

async def test_apply_org_rejects_bad_image(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    r = await client.post(
        "/orgs",
        data=FORM,
        files={"signature": ("s.gif", b"GIF89a....", "image/gif")},
        headers=dev(user),
    )
    assert r.status_code == 422 and r.json()["code"] == "signature_not_png"
    r = await client.post("/orgs", data={**FORM, "inn": "12"}, headers=dev(user))
    assert r.json()["code"] == "invalid_inn"

async def test_operator_verify_and_reject(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operator = await make_user(db_session, is_operator=True)
    pending = await make_org(db_session, status=OrgStatus.PENDING)
    other = await make_org(db_session, status=OrgStatus.PENDING)
    await make_org(db_session)

    r = await client.get("/operator/orgs", params={"status": "pending"}, headers=dev(operator))
    assert {o["id"] for o in r.json()} == {str(pending.id), str(other.id)}

    point = {"lat": 55.79, "lon": 49.12}
    r = await client.post(f"/operator/orgs/{pending.id}/verify", json=point, headers=dev(operator))
    assert r.status_code == 200 and r.json()["status"] == "verified"
    r = await client.post(f"/operator/orgs/{pending.id}/verify", json=point, headers=dev(operator))
    assert r.status_code == 409

    r = await client.post(
        f"/operator/orgs/{other.id}/reject", json={"reason": "Нет ИНН"}, headers=dev(operator)
    )
    assert r.json()["status"] == "rejected" and r.json()["rejectReason"] == "Нет ИНН"

    jobs = list(await db_session.scalars(select(Job).where(Job.kind == "notify.org_review")))
    assert sorted(j.payload["org_id"] for j in jobs) == sorted([str(pending.id), str(other.id)])

    r = await client.post(
        "/operator/orgs/00000000-0000-0000-0000-000000000000/verify",
        json=point,
        headers=dev(operator),
    )
    assert r.status_code == 404

async def test_operator_only(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    r = await client.get("/operator/orgs", headers=dev(team.owner))
    assert r.status_code == 403 and r.json()["code"] == "not_operator"
    r = await client.get("/operator/metrics", headers=dev(team.owner))
    assert r.status_code == 403

async def test_operator_metrics_lists_all(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operator = await make_user(db_session, is_operator=True)
    r = await client.get("/operator/metrics", headers=dev(operator))
    assert r.status_code == 200
    assert r.json()["periodLabel"] == "Пилот · за 6 недель"
