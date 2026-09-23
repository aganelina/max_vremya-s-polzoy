import pytest
from pydantic import ValidationError

from app.config import Settings

PROD = {
    "app_env": "prod",
    "max_bot_token": "123:abc",
    "max_webhook_secret": "hook-secret",
    "public_base_url": "https://vremya.example.ru",
}

def test_dev_auth_only_on_local_url() -> None:
    assert Settings(app_env="dev", public_base_url="http://localhost:8080").dev_auth_enabled
    with pytest.raises(ValidationError, match="APP_ENV=dev"):
        Settings(app_env="dev", public_base_url="https://vremya.example.ru")

def test_prod_disables_dev_auth() -> None:
    assert not Settings(**PROD).dev_auth_enabled  # type: ignore[arg-type]

@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"max_bot_token": ""}, "MAX_BOT_TOKEN"),
        ({"max_webhook_secret": ""}, "MAX_WEBHOOK_SECRET"),
        ({"public_base_url": "http://localhost:8080"}, "PUBLIC_BASE_URL"),
        ({"public_base_url": "http://vremya.example.ru"}, "PUBLIC_BASE_URL"),
    ],
)
def test_prod_requires_bot_secret_and_https(override: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**{**PROD, **override})  # type: ignore[arg-type]

def test_retry_policy_outlasts_long_max_outage() -> None:
    settings = Settings(app_env="test")
    delays = [
        min(settings.worker_retry_base_seconds * 2**n, settings.worker_retry_max_seconds)
        for n in range(settings.worker_max_attempts - 1)
    ]
    assert settings.worker_max_attempts == 12
    assert max(delays) == 3600
    assert sum(delays) >= 8 * 3600
