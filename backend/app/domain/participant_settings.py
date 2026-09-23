from datetime import time
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ParticipantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    fallback_evening: time = time(17, 30)
    fallback_weekend: time = time(11, 0)
    checkin_before_min: int = 15
    checkin_after_min: int = 30
    late_after_min: int = 10
    cert_sign_key_path: str = ""
    cert_sign_cert_path: str = ""
    cert_sign_key_passphrase: str = ""
    check_rate_per_min: int = 30
    checkin_rate_per_min: int = 5
    schedule_max_bytes: int = 1_000_000
    schedule_horizon_days: int = 60

@lru_cache
def participant_settings() -> ParticipantSettings:
    return ParticipantSettings()
