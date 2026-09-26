import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.seed import seed_demo
from app.seed.ids import demo_id
from tests.conftest import NOW
from tests.support import dev


async def test_seed_serves_coordinator_screens(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    for _ in range(2):
        async with db.transaction() as session:
            await seed_demo(session, NOW)

    home = (await client.get("/coord/home", headers=dev(1))).json()
    assert home["next"]["shift"]["id"] == str(demo_id("s-books"))
    assert home["next"]["shift"]["booked"] == 5

    att = (
        await client.get(f"/coord/shifts/{demo_id('s-books')}/attendance", headers=dev(1))
    ).json()
    assert [(p["firstName"], p["status"]) for p in att["participants"]] == [
        ("Алина", "came"),
        ("Тимур", "late"),
        ("Софья", "booked"),
        ("Марат", "booked"),
        ("Ильдар", "no_show"),
    ]

    reviews = (await client.get("/coord/reviews", headers=dev(1))).json()
    assert [i["authorName"] for i in reviews["items"]] == ["Камила", "Руслан", "Алина"]

    access = (await client.get("/coord/access", headers=dev(1))).json()
    assert access["orgName"] == "Книжный мост (демо)"
    assert access["coordinators"][0]["name"] == "Алина"
    assert {"Гульнара", "Ринат"} <= {c["name"] for c in access["coordinators"]}

    metrics = (await client.get("/coord/metrics", headers=dev(1))).json()
    assert metrics["orgs"][0]["name"] == "Книжный мост (демо)"
    assert metrics["orgs"][-1]["name"] == "В среднем по пилоту"
    assert metrics["participants"] >= 3
