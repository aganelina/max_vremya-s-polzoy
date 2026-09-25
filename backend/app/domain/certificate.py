import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import CertPeriod
from app.db.models import Certificate, Org, University, User
from app.domain.credits import credited_rows
from app.domain.hours import local_midnight, semester_start

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def new_code() -> str:
    chars = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    return f"{chars[:3]}-{chars[3:]}"

def normalize_code(raw: str) -> str | None:
    value = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(value) != 6 or any(ch not in CODE_ALPHABET for ch in value):
        return None
    return f"{value[:3]}-{value[3:]}"

def period_start(period: CertPeriod, today: date) -> date | None:
    return semester_start(today) if period is CertPeriod.SEMESTER else None

_MONTHS_GEN = {9: "сентября", 2: "февраля"}

def period_label(period: CertPeriod, today: date) -> str:
    start = period_start(period, today)
    if start is None:
        return "всё время"
    return f"с {start.day} {_MONTHS_GEN[start.month]}"

def verify_base_url() -> str:
    base = get_settings().public_base_url.rstrip("/")
    return base.split("://", 1)[-1] + "/check"

def verify_full_url(code: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/check/{code}"

def _snapshot(rows: list[Any]) -> tuple[list[dict[str, Any]], Decimal]:
    snap = [
        {
            "date": r.date.isoformat(),
            "title": r.title,
            "org": r.org_name,
            "orgId": str(r.org_id) if r.org_id else None,
            "hours": str(r.hours),
        }
        for r in rows
    ]
    total = sum((Decimal(r.hours) for r in rows), Decimal(0))
    return snap, total

async def ensure_certificate(
    session: AsyncSession, user: User, period: CertPeriod, now: datetime
) -> Certificate:
    tz = get_settings().tz
    start = period_start(period, now.astimezone(tz).date())
    since = local_midnight(start, tz) if start is not None else None
    snap, total = _snapshot(await credited_rows(session, user.id, since))
    last = await session.scalar(
        select(Certificate)
        .where(
            Certificate.user_id == user.id,
            Certificate.period == period,
            Certificate.revoked_at.is_(None),
        )
        .order_by(Certificate.generated_at.desc())
        .limit(1)
    )
    if last is not None and last.rows == snap and Decimal(last.total) == total:
        return last
    for _ in range(5):
        cert = Certificate(
            user_id=user.id,
            code=new_code(),
            period=period,
            rows=snap,
            total=total,
            generated_at=now,
        )
        try:
            async with session.begin_nested():
                session.add(cert)
                await session.flush()
        except IntegrityError:
            continue
        return cert
    raise RuntimeError("certificate code collision")

@dataclass(frozen=True)
class Signer:
    org: str
    position: str
    name: str
    signature_png: bytes | None
    seal_png: bytes | None

@dataclass(frozen=True)
class CertificateData:
    first_name: str
    university: str
    period_label: str
    generated_at: datetime
    rows: list[dict[str, Any]]
    total: Decimal
    code: str
    verify_url: str
    signers: list[Signer]

async def certificate_data(session: AsyncSession, cert: Certificate) -> CertificateData:
    user = await session.get(User, cert.user_id) if cert.user_id else None
    university = (
        await session.get(University, user.university_id)
        if user is not None and user.university_id
        else None
    )
    org_ids = list(dict.fromkeys(uuid.UUID(r["orgId"]) for r in cert.rows if r.get("orgId")))
    orgs = (
        {o.id: o for o in await session.scalars(select(Org).where(Org.id.in_(org_ids)))}
        if org_ids
        else {}
    )
    signers = [
        Signer(
            org=o.name,
            position=o.sign_position or "",
            name=o.sign_name or "",
            signature_png=o.signature_image,
            seal_png=o.seal_image,
        )
        for oid in org_ids
        if (o := orgs.get(oid)) is not None
    ]
    tz = get_settings().tz
    return CertificateData(
        first_name=user.first_name if user else "",
        university=university.name if university else "",
        period_label=period_label(cert.period, cert.generated_at.astimezone(tz).date()),
        generated_at=cert.generated_at,
        rows=cert.rows,
        total=Decimal(cert.total),
        code=cert.code,
        verify_url=verify_full_url(cert.code),
        signers=signers,
    )

async def certificate_pdf(session: AsyncSession, certificate_id: uuid.UUID) -> bytes:
    import asyncio

    from app.domain.certificate_pdf import render_pdf
    from app.domain.pdf_signing import sign_pdf

    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise LookupError("certificate not found")
    data = await certificate_data(session, cert)

    def _build() -> bytes:
        return sign_pdf(render_pdf(data, get_settings().tz))

    pdf = await asyncio.to_thread(_build)
    cert.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
    await session.flush()
    return pdf
