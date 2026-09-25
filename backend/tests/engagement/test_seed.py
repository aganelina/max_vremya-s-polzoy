import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.seed import seed_demo
from tests.conftest import NOW
from tests.support import dev


async def test_demo_matches_mock(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    for _ in range(2):
        async with db.transaction() as session:
            await seed_demo(session, NOW)

    task = (await client.get("/micro-tasks/next", headers=dev(1))).json()
    assert task["title"] == "Проверь текст объявления о пристройстве собак"
    assert task["status"] == "free"

    bank = (await client.get("/bank", headers=dev(1))).json()
    assert bank["balance"] == 2.5
    assert [r["text"] for r in bank["others"]] == [
        "Подменить на стойке регистрации конференции",
        "Помочь собрать шкаф в общежитии",
    ]
    assert bank["mine"][0]["helperName"] == "Артур"
    assert bank["mine"][0]["status"] == "matched"
    assert bank["mine"][0]["district"] == "Вахитовский район"

    mentorship = (await client.get("/mentorship", headers=dev(1))).json()
    assert mentorship["eligible"] is True and mentorship["accepting"] is True
    assert [r["newbieName"] for r in mentorship["requests"]] == ["Камила"]
    assert mentorship["requests"][0]["deal"]["title"] == "Уборка сквера у озера Кабан (демо)"
    assert [p["newbieName"] for p in mentorship["pairs"]] == ["Руслан"]

    me = (await client.get("/me", headers=dev(1))).json()
    assert me["stats"]["bankBalance"] == 2.5
