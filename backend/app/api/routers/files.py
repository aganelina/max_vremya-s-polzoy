import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import AwareDatetime

from app.api.errors import NotFound
from app.api.schemas.base import CamelModel
from app.api.throttle import SlidingWindow
from app.auth.deps import DbSession, Now, active_membership, is_onboarded
from app.db.enums import CertPeriod
from app.db.models import User
from app.domain import file_links
from app.domain.participant_settings import participant_settings

router = APIRouter(tags=["files"])

files_limiter = SlidingWindow(participant_settings().check_rate_per_min)

class FileLink(CamelModel):
    url: str
    file_name: str
    expires_at: AwareDatetime

def make_file_link(payload: dict[str, Any], file_name: str, now: datetime) -> FileLink:
    token, expires_at = file_links.sign(payload, now)
    return FileLink(url=file_links.file_url(token), file_name=file_name, expires_at=expires_at)

def _attachment(content: bytes, media_type: str, file_name: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )

def _uuid(raw: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise NotFound() from None

def _day(raw: object) -> date:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise NotFound() from None

async def _user(session: DbSession, raw: object) -> User:
    user = await session.get(User, _uuid(raw))
    if user is None or not is_onboarded(user):
        raise NotFound()
    return user

async def _certificate(session: DbSession, data: dict[str, Any], now: datetime) -> Response:
    from app.domain.certificate import certificate_pdf, ensure_certificate

    user = await _user(session, data.get("u"))
    try:
        period = CertPeriod(str(data.get("p")))
    except ValueError:
        raise NotFound() from None
    cert = await ensure_certificate(session, user, period, now)
    pdf = await certificate_pdf(session, cert.id)
    await session.commit()
    return _attachment(pdf, "application/pdf", f"spravka-{cert.code}.pdf")

async def _attendance(session: DbSession, data: dict[str, Any]) -> Response:
    from app.api.routers.coord import attendance_csv_bytes, attendance_file_name

    user = await _user(session, data.get("u"))
    org_id = _uuid(data.get("o"))
    found = await active_membership(session, user)
    if found is None or found[1].id != org_id:
        raise NotFound()
    day_from, day_to = _day(data.get("f")), _day(data.get("t"))
    content = await attendance_csv_bytes(session, org_id, day_from, day_to)
    return _attachment(content, "text/csv; charset=utf-8", attendance_file_name(day_from, day_to))

@router.get("/files/{token}", include_in_schema=False)
async def download(token: str, request: Request, session: DbSession, now: Now) -> Response:
    ip = request.client.host if request.client else "unknown"
    if not files_limiter.allow(ip):
        return Response("Слишком много попыток", status_code=429, media_type="text/plain")
    data = file_links.verify(token, now)
    if data is None:
        raise NotFound()
    kind = data.get("k")
    if kind == "certificate":
        return await _certificate(session, data, now)
    if kind == "attendance":
        return await _attendance(session, data)
    raise NotFound()
