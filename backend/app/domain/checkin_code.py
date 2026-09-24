import hashlib
import hmac
import os
import re
import struct
from dataclasses import dataclass
from datetime import UTC, datetime

STEP_SECONDS = 60
DIGITS = 6
QR_PREFIX = "vremya:checkin:"

_CODE_RE = re.compile(r"^\d{6}$")

def new_secret() -> bytes:
    return os.urandom(20)

def _counter(at: datetime) -> int:
    return int(at.timestamp()) // STEP_SECONDS

def _hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)

def totp(secret: bytes, at: datetime) -> str:
    return _hotp(secret, _counter(at))

@dataclass(frozen=True)
class CheckinCode:
    code: str
    qr_payload: str
    expires_at: datetime

def current_code(secret: bytes, now: datetime) -> CheckinCode:
    counter = _counter(now)
    code = _hotp(secret, counter)
    expires_at = datetime.fromtimestamp((counter + 1) * STEP_SECONDS, tz=UTC)
    return CheckinCode(code=code, qr_payload=QR_PREFIX + code, expires_at=expires_at)

def normalize(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith(QR_PREFIX):
        value = value[len(QR_PREFIX) :]
    value = value.replace(" ", "")
    return value if _CODE_RE.match(value) else None

class CodeCheck:
    OK = "ok"
    EXPIRED = "expired"
    WRONG = "wrong_code"

_EXPIRED_LOOKBACK = 10

def check(secret: bytes, raw: str, now: datetime) -> str:
    code = normalize(raw)
    if code is None:
        return CodeCheck.WRONG
    counter = _counter(now)
    for back in range(2):
        if hmac.compare_digest(_hotp(secret, counter - back), code):
            return CodeCheck.OK
    for back in range(2, _EXPIRED_LOOKBACK + 1):
        if hmac.compare_digest(_hotp(secret, counter - back), code):
            return CodeCheck.EXPIRED
    return CodeCheck.WRONG

def verify(secret: bytes, raw: str, now: datetime) -> bool:
    return check(secret, raw, now) == CodeCheck.OK
