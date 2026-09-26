import re

from app.domain.coord import CoordError

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 1024 * 1024
_INN = re.compile(r"^\d{10}(\d{2})?$")
_PHONE = re.compile(r"^\+?[\d\s()\-]{5,20}$")
NAME_MAX = 200

def clean_text(value: str | None, code: str, *, required: bool, max_len: int = NAME_MAX) -> str:
    text = (value or "").strip()
    if (required and not text) or len(text) > max_len:
        raise CoordError(422, code)
    return text

def clean_inn(value: str | None) -> str | None:
    inn = (value or "").strip()
    if not inn:
        return None
    if not _INN.match(inn):
        raise CoordError(422, "invalid_inn")
    return inn

def clean_phone(value: str | None) -> str:
    phone = (value or "").strip()
    if not _PHONE.match(phone):
        raise CoordError(422, "invalid_phone")
    return phone

def check_png(data: bytes, field: str) -> bytes:
    if len(data) > MAX_IMAGE_BYTES:
        raise CoordError(422, f"{field}_too_large")
    if not data.startswith(PNG_MAGIC):
        raise CoordError(422, f"{field}_not_png")
    return data
