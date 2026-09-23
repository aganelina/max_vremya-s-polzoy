import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import deps
from app.config import Settings
from tests.factories import make_user

TOKEN = "student-review-0123456789"

def _prod(monkeypatch: pytest.MonkeyPatch, accounts: str) -> None:
    settings = Settings(
        app_env="prod",
        max_bot_token="x",
        max_webhook_secret="hook-secret",
        public_base_url="https://vremya.example.ru",
        test_accounts=accounts,
    )
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

async def test_bearer_token_logs_in_existing_user_in_prod(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await make_user(db_session, first_name="Проверяющий")
    _prod(monkeypatch, f"{TOKEN}:{user.max_user_id}")

    resp = await client.get("/me", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200 and resp.json()["firstName"] == "Проверяющий"

    resp = await client.get("/me", headers={"Authorization": "Bearer wrong-token-0123456789"})
    assert resp.status_code == 401

async def test_bearer_disabled_when_not_configured(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_user(db_session)
    _prod(monkeypatch, "")
    resp = await client.get("/me", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 401

async def test_bearer_for_unknown_user(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prod(monkeypatch, f"{TOKEN}:987654321")
    resp = await client.get("/me", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 401 and resp.json()["code"] == "test_account_unknown"

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("test_accounts", "short:1"),
        ("test_accounts", "no-colon-token-xxxx"),
        ("max_webhook_secret", "bad secret!"),
    ],
)
def test_settings_validation(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="test", **{field: value})  # type: ignore[arg-type]

def test_webhook_secret_ok() -> None:
    assert Settings(app_env="test", max_webhook_secret="vremya_hook-2026").max_webhook_secret
