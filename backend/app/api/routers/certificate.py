from html import escape
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.routers.files import FileLink, make_file_link
from app.api.schemas.deals import Certificate, CertificateRow, Participant, ShareIn
from app.api.throttle import SlidingWindow
from app.auth.deps import DbSession, Now, OnboardedUser
from app.config import get_settings
from app.db.enums import CertPeriod
from app.db.models import Certificate as CertificateModel
from app.db.models import University, User
from app.domain.certificate import (
    certificate_pdf,
    ensure_certificate,
    normalize_code,
    period_label,
    verify_base_url,
)
from app.domain.hours import to_hours
from app.domain.participant_settings import participant_settings
from app.worker.queue import enqueue

router = APIRouter(tags=["certificate"])
check_router = APIRouter(tags=["check"])

check_limiter = SlidingWindow(participant_settings().check_rate_per_min)

PeriodQ = Annotated[Literal["semester", "all"], Query()]

@router.get("/me/certificate", response_model=Certificate)
async def get_certificate(
    user: OnboardedUser, session: DbSession, now: Now, period: PeriodQ = "semester"
) -> Certificate:
    cert = await ensure_certificate(session, user, CertPeriod(period), now)
    await session.commit()
    university = await session.get(University, user.university_id) if user.university_id else None
    tz = get_settings().tz
    return Certificate(
        period=period,
        period_label=period_label(cert.period, now.astimezone(tz).date()),
        generated_at=cert.generated_at,
        participant=Participant(
            first_name=user.first_name, university=university.name if university else ""
        ),
        rows=[
            CertificateRow(
                date=r["date"], title=r["title"], org=r["org"], hours=to_hours(r["hours"])
            )
            for r in cert.rows
        ],
        total=to_hours(cert.total),
        verify_code=cert.code,
        verify_url=verify_base_url(),
    )

@router.get("/me/certificate.pdf")
async def get_certificate_pdf(
    user: OnboardedUser, session: DbSession, now: Now, period: PeriodQ = "semester"
) -> Response:
    cert = await ensure_certificate(session, user, CertPeriod(period), now)
    pdf = await certificate_pdf(session, cert.id)
    await session.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="spravka-{cert.code}.pdf"'},
    )

@router.post("/me/certificate/link", response_model=FileLink)
async def certificate_link(
    user: OnboardedUser, session: DbSession, now: Now, period: PeriodQ = "semester"
) -> FileLink:
    """Короткоживущая ссылка на PDF — для WebApp.downloadFile в MAX (blob: там не работает)."""
    cert = await ensure_certificate(session, user, CertPeriod(period), now)
    await session.commit()
    return make_file_link(
        {"k": "certificate", "u": str(user.id), "p": period},
        f"spravka-{cert.code}.pdf",
        now,
    )

@router.post("/me/certificate/share", status_code=204)
async def share_certificate(
    user: OnboardedUser, session: DbSession, now: Now, body: ShareIn | None = None
) -> Response:
    """PDF в чат MAX присылает бот (notify.certificate → certificate_pdf)."""
    period = (body or ShareIn()).period
    cert = await ensure_certificate(session, user, CertPeriod(period), now)
    await enqueue(session, "notify.certificate", {"certificate_id": str(cert.id)})
    await session.commit()
    return Response(status_code=204)

_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Проверка справки · Время с пользой</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f5f5f2;color:#1d1d1b}}
main{{max-width:480px;margin:48px auto;padding:24px;background:#fff;border-radius:16px}}
h1{{font-size:22px;margin:0 0 16px}} .ok{{color:#1f7a3f}} .bad{{color:#b3261e}}
dl{{margin:0}} dt{{color:#6b6b66;font-size:13px;margin-top:12px}}
dd{{margin:2px 0 0;font-size:17px}}
</style></head><body><main>{body}</main></body></html>"""

def _page(body: str, status: int) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(body=body), status_code=status)

@check_router.get("/check/{code}", response_class=HTMLResponse, include_in_schema=False)
async def check_page(code: str, request: Request, session: DbSession) -> HTMLResponse:
    ip = request.client.host if request.client else "unknown"
    if not check_limiter.allow(ip):
        return _page(
            '<h1 class="bad">Слишком много попыток</h1><p>Попробуйте через минуту.</p>', 429
        )
    normalized = normalize_code(code)
    cert = (
        await session.scalar(select(CertificateModel).where(CertificateModel.code == normalized))
        if normalized
        else None
    )
    if cert is None:
        return _page('<h1 class="bad">Справка не найдена</h1><p>Проверьте код.</p>', 404)
    user = await session.get(User, cert.user_id) if cert.user_id else None
    if cert.revoked_at is not None or user is None:
        title = "Справка аннулирована — сформируйте новую" if user else "Справка аннулирована"
        return _page(f'<h1 class="bad">{title}</h1><p>Код {escape(cert.code)}</p>', 200)
    university = await session.get(University, user.university_id) if user.university_id else None
    tz = get_settings().tz
    generated = cert.generated_at.astimezone(tz)
    items = [
        ("Имя", user.first_name),
        ("Вуз", university.name if university else "—"),
        ("Период", period_label(cert.period, generated.date())),
        ("Итого часов", f"{to_hours(cert.total):g}".replace(".", ",")),
        ("Сформирована", generated.strftime("%d.%m.%Y")),
    ]
    rows = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in items)
    return _page(f'<h1 class="ok">Справка действительна</h1><dl>{rows}</dl>', 200)
