import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_ENVIRONMENTS = ("dev", "test")
_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{5,256}")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "prod"
    database_url: str = "postgresql+asyncpg://vremya:vremya@127.0.0.1:54330/vremya"
    public_base_url: str = "http://localhost:8080"
    timezone: str = "Europe/Moscow"

    max_bot_token: str = ""
    max_webhook_secret: str = ""
    test_accounts: str = ""
    max_bot_username: str = ""
    init_data_max_age_seconds: int = 24 * 3600
    init_data_clock_skew_seconds: int = 60

    pause_days: int = 7
    mentor_min_deals: int = 3
    cancel_hours_before: int = 3
    instructions_hour: int = 19

    worker_poll_interval_seconds: float = 1.0
    worker_retry_base_seconds: float = 300.0
    worker_retry_max_seconds: float = 3600.0
    worker_max_attempts: int = 12
    worker_backlog_warn: int = 50

    def test_account_pairs(self) -> list[tuple[str, int]]:
        pairs = []
        for chunk in self.test_accounts.split(","):
            token, sep, max_id = chunk.strip().rpartition(":")
            if not chunk.strip():
                continue
            if not sep or not token or not max_id.isdigit():
                raise ValueError("TEST_ACCOUNTS: формат «токен:max_user_id» через запятую")
            pairs.append((token, int(max_id)))
        return pairs

    @property
    def dev_auth_enabled(self) -> bool:
        return self.app_env in _DEV_ENVIRONMENTS

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @model_validator(mode="after")
    def _check_prod(self) -> "Settings":
        if self.app_env == "prod" and not self.max_bot_token:
            raise ValueError(
                "MAX_BOT_TOKEN обязателен при APP_ENV=prod: без него initData не проверить"
            )
        if self.app_env == "prod" and not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL при APP_ENV=prod — только https://<домен>")
        if self.app_env == "prod" and not self.max_webhook_secret:
            raise ValueError(
                "MAX_WEBHOOK_SECRET обязателен при APP_ENV=prod: без него webhook отвергает всё"
            )
        if self.max_webhook_secret and not _WEBHOOK_SECRET.fullmatch(self.max_webhook_secret):
            raise ValueError(
                "MAX_WEBHOOK_SECRET: 5–256 символов, только A-Z a-z 0-9 _ - (требование MAX)"
            )
        for token, _ in self.test_account_pairs():
            if len(token) < 16:
                raise ValueError(
                    "TEST_ACCOUNTS: токен тестовой учётной записи — не короче 16 символов"
                )
        if self.dev_auth_enabled and self.app_env == "dev" and not _is_local(self.public_base_url):
            raise ValueError("APP_ENV=dev разрешён только с локальным PUBLIC_BASE_URL")
        return self

def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")

@lru_cache
def get_settings() -> Settings:
    return Settings()
