from pathlib import Path

import httpx
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session as db
from app.seed import seed_demo
from tests.conftest import NOW

SPEC = Path(__file__).resolve().parents[2] / "DATA-API.yaml"

async def test_submission_checks(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    document = yaml.safe_load(SPEC.read_text())
    roles = {role["id"]: role["test_account"]["max_user_id"] for role in document["roles"]}
    settings = get_settings()
    original = settings.test_accounts
    tokens = {role: f"audit-account-token-{role}" for role in roles}
    settings.test_accounts = ",".join(f"{tokens[role]}:{uid}" for role, uid in roles.items())
    try:
        async with db.transaction() as session:
            await seed_demo(session, NOW)
        for check in document["required_checks"]:
            role = check["role"]
            headers = {} if role == "none" else {"Authorization": f"Bearer {tokens[role]}"}
            response = await client.request(
                check["method"],
                check["path"],
                headers=headers,
                params=check.get("query"),
                json=check.get("body"),
            )
            assert response.status_code in check["expect_status"], (check["id"], response.text)
            expected = check["response"]
            assert response.headers["content-type"].split(";")[0] == expected["content_type"]
            assert set(expected["required_fields"]) <= response.json().keys(), check["id"]
    finally:
        settings.test_accounts = original
