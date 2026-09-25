from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import HelpStatus, LedgerSource
from app.db.models import HelpRequest, HourLedger, Job
from tests.conftest import NOW
from tests.engagement.helpers import make_request
from tests.factories import credit, make_user
from tests.support import dev

BANK_KEYS = {"balance", "reserved", "maxOpenRequests", "others", "mine"}
REQUEST_KEYS = {
    "id",
    "text",
    "hours",
    "when",
    "district",
    "mine",
    "responded",
    "helperName",
    "status",
}

async def test_bank_view(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    me = await make_user(db_session, first_name="Алина")
    neighbor = await make_user(db_session)
    await credit(db_session, me, "3", NOW)
    await credit(db_session, me, "-1", NOW, LedgerSource.BANK_SPEND)
    await credit(db_session, me, "0.5", NOW, LedgerSource.BANK_HELP)
    theirs = await make_request(db_session, neighbor)
    await make_request(db_session, neighbor, district="d5")
    await make_request(db_session, neighbor, status=HelpStatus.CLOSED)
    mine = await make_request(db_session, me)

    resp = await client.get("/bank", headers=dev(me))
    assert resp.status_code == 200
    bank = resp.json()
    assert set(bank) == BANK_KEYS
    assert bank["balance"] == 2.5
    assert bank["reserved"] == 1
    assert bank["maxOpenRequests"] == 3
    assert [r["id"] for r in bank["others"]] == [str(theirs.id)]
    other = bank["others"][0]
    assert set(other) == REQUEST_KEYS
    assert other == {
        "id": str(theirs.id),
        "text": "Помочь с переездом",
        "hours": 1,
        "when": "суббота",
        "district": "Вахитовский район",
        "mine": False,
        "responded": False,
        "helperName": None,
        "status": "open",
    }
    assert [r["id"] for r in bank["mine"]] == [str(mine.id)]
    assert bank["mine"][0]["mine"] is True

async def test_respond_and_withdraw(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    author = await make_user(db_session, first_name="Динара")
    helper = await make_user(db_session, first_name="Артур")
    second = await make_user(db_session, first_name="Тимур")
    request = await make_request(db_session, author)

    resp = await client.put(f"/bank/requests/{request.id}/response", headers=dev(helper))
    assert resp.status_code == 200
    other = resp.json()["others"][0]
    assert other["responded"] is True and other["status"] == "matched"
    await client.put(f"/bank/requests/{request.id}/response", headers=dev(helper))
    jobs = (await db_session.scalars(select(Job).where(Job.kind == "notify.bank_response"))).all()
    assert [j.payload for j in jobs] == [
        {"request_id": str(request.id), "helper_id": str(helper.id)}
    ]
    await client.put(f"/bank/requests/{request.id}/response", headers=dev(second))

    author_view = (await client.get("/bank", headers=dev(author))).json()["mine"][0]
    assert author_view["helperName"] == "Артур" and author_view["responded"] is True

    resp = await client.delete(f"/bank/requests/{request.id}/response", headers=dev(helper))
    assert resp.status_code == 200
    assert resp.json()["others"] == []
    await db_session.refresh(request)
    assert request.helper_id == second.id and request.status is HelpStatus.MATCHED
    await client.delete(f"/bank/requests/{request.id}/response", headers=dev(second))
    await db_session.refresh(request)
    assert request.helper_id is None and request.status is HelpStatus.OPEN

async def test_respond_own_or_closed(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    author = await make_user(db_session)
    other = await make_user(db_session)
    request = await make_request(db_session, author)
    own = await client.put(f"/bank/requests/{request.id}/response", headers=dev(author))
    assert own.status_code == 404
    closed = await make_request(db_session, author, status=HelpStatus.CLOSED)
    resp = await client.put(f"/bank/requests/{closed.id}/response", headers=dev(other))
    assert resp.status_code == 409
    assert resp.json() == {"code": "request_closed"}

async def test_ask_help(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    me = await make_user(db_session)
    await credit(db_session, me, "2", NOW)
    resp = await client.post(
        "/bank/requests", json={"text": " Донести коробки ", "hours": 1}, headers=dev(me)
    )
    assert resp.status_code == 200
    mine = resp.json()["mine"]
    assert len(mine) == 1
    assert mine[0]["text"] == "Донести коробки"
    assert mine[0]["when"] == "когда удобно"
    assert mine[0]["status"] == "open" and mine[0]["helperName"] is None

    over = await client.post(
        "/bank/requests", json={"text": "Много", "hours": 2.5}, headers=dev(me)
    )
    assert over.status_code == 409
    assert over.json() == {"code": "insufficient_balance"}

    for _ in range(2):
        ok = await client.post(
            "/bank/requests", json={"text": "Ещё", "hours": 0.5}, headers=dev(me)
        )
        assert ok.status_code == 200
    limit = await client.post("/bank/requests", json={"text": "Ещё", "hours": 0.5}, headers=dev(me))
    assert limit.status_code == 409
    assert limit.json() == {"code": "too_many_requests"}

    bad = await client.post("/bank/requests", json={"text": "  ", "hours": 1}, headers=dev(me))
    assert bad.status_code == 422

async def test_received_moves_hours(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    author = await make_user(db_session)
    helper = await make_user(db_session)
    await credit(db_session, author, "3", NOW)
    open_request = await make_request(db_session, author)
    no_helper = await client.post(f"/bank/requests/{open_request.id}/received", headers=dev(author))
    assert no_helper.status_code == 409
    assert no_helper.json() == {"code": "no_helper"}

    request = await make_request(
        db_session, author, hours="1.5", status=HelpStatus.MATCHED, helper=helper
    )
    foreign = await client.post(f"/bank/requests/{request.id}/received", headers=dev(helper))
    assert foreign.status_code == 404

    resp = await client.post(f"/bank/requests/{request.id}/received", headers=dev(author))
    assert resp.status_code == 200
    assert resp.json()["balance"] == 1.5
    closed = next(r for r in resp.json()["mine"] if r["id"] == str(request.id))
    assert closed["status"] == "closed"
    again = await client.post(f"/bank/requests/{request.id}/received", headers=dev(author))
    assert again.json()["balance"] == 1.5

    rows = (
        await db_session.execute(
            select(HourLedger.user_id, HourLedger.source, HourLedger.hours).where(
                HourLedger.ref_id == request.id
            )
        )
    ).all()
    assert set(rows) == {
        (author.id, LedgerSource.BANK_SPEND, Decimal("-1.5")),
        (helper.id, LedgerSource.BANK_HELP, Decimal("1.5")),
    }
    helper_bank = (await client.get("/bank", headers=dev(helper))).json()
    assert helper_bank["balance"] == 1.5
    status = await db_session.scalar(select(HelpRequest.status).where(HelpRequest.id == request.id))
    assert status is HelpStatus.CLOSED
