import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings

LINK_TTL = timedelta(minutes=5)
_DEV_KEY = b"vremya-dev-file-links"

def _key() -> bytes:
    settings = get_settings()
    secret = f"{settings.max_bot_token}\x00{settings.max_webhook_secret}"
    if not settings.max_bot_token and not settings.max_webhook_secret:
        return _DEV_KEY
    return hashlib.sha256(b"file-links\x00" + secret.encode()).digest()

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def _sign(body: str) -> str:
    return _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())

def sign(payload: dict[str, Any], now: datetime) -> tuple[str, datetime]:
    exp = int((now + LINK_TTL).timestamp())
    expires_at = datetime.fromtimestamp(exp, UTC)
    data = {**payload, "exp": exp}
    body = _b64(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_sign(body)}", expires_at

def verify(token: str, now: datetime) -> dict[str, Any] | None:
    body, sep, sig = token.partition(".")
    if not sep or not body or not hmac.compare_digest(sig.encode(), _sign(body).encode()):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, binascii.Error):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("exp"), int):
        return None
    if data["exp"] <= now.timestamp():
        return None
    return data

def file_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/files/{token}"
