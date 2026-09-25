import asyncio
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import httpx
from fastapi import FastAPI
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation.pdf_embedded import async_validate_pdf_signature
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, LedgerSource, OrgRole
from app.db.models import Certificate, HourLedger, MaxChat, SearchLog, User
from app.domain.metrics import compute_metrics
from app.domain.participant_settings import participant_settings
from app.domain.pdf_signing import generate_self_signed, reset_signer
from tests.conftest import NOW
from tests.deals.helpers import book, jobs, make_org, make_shift, msk
from tests.factories import add_member, make_user
from tests.support import dev

CERT_KEYS = {
    "period",
    "periodLabel",
    "generatedAt",
    "participant",
    "rows",
    "total",
    "verifyCode",
    "verifyUrl",
}

async def _credited(db_session: AsyncSession, user: User) -> None:
    org = await make_org(db_session)
    for days, hours in ((10, "1.5"), (200, "2.0")):
        shift = await make_shift(db_session, org, NOW - timedelta(days=days), title=f"Дело {days}")
        booking = await book(db_session, shift, user, BookingStatus.DONE)
        db_session.add(
            HourLedger(
                user_id=user.id,
                source=LedgerSource.SHIFT,
                ref_id=booking.id,
                hours=Decimal(hours),
                org_id=org.id,
                accepted_at=NOW - timedelta(days=days),
            )
        )
    await db_session.commit()

async def test_certificate_json_pdf_share(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, first_name="Алина")
    await _credited(db_session, user)

    data = (await client.get("/me/certificate", headers=dev(user))).json()
    assert set(data) == CERT_KEYS
    assert data["period"] == "semester" and data["periodLabel"] == "с 1 сентября"
    assert data["participant"] == {"firstName": "Алина", "university": "КФУ"}
    assert [r["title"] for r in data["rows"]] == ["Дело 10"]
    assert data["total"] == 1.5
    assert data["verifyUrl"].endswith("/check")
    again = (await client.get("/me/certificate", headers=dev(user))).json()
    assert again["verifyCode"] == data["verifyCode"]
    full = (await client.get("/me/certificate", headers=dev(user), params={"period": "all"})).json()
    assert full["total"] == 3.5 and full["verifyCode"] != data["verifyCode"]

    resp = await client.get("/me/certificate.pdf", headers=dev(user))
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/pdf"
    reader = PdfFileReader(BytesIO(resp.content))
    status = await async_validate_pdf_signature(reader.embedded_signatures[0])
    assert status.intact and status.valid

    resp = await client.post("/me/certificate/share", headers=dev(user), json={"period": "all"})
    assert resp.status_code == 204
    queued = await jobs(db_session, "notify.certificate")
    cert = await db_session.scalar(
        select(Certificate).where(Certificate.code == full["verifyCode"])
    )
    assert cert is not None and queued[0].payload == {"certificate_id": str(cert.id)}

    resp = await client.get("/me/certificate", headers=dev(user), params={"period": "year"})
    assert resp.status_code == 422

async def test_signing_with_configured_cert(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.domain.pdf_signing import sign_pdf

    key, cert = generate_self_signed("Test platform")
    (tmp_path / "k.pem").write_bytes(key)
    (tmp_path / "c.pem").write_bytes(cert)
    ps = participant_settings()
    monkeypatch.setattr(ps, "cert_sign_key_path", str(tmp_path / "k.pem"))
    monkeypatch.setattr(ps, "cert_sign_cert_path", str(tmp_path / "c.pem"))
    reset_signer()
    try:
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 100, "x")
        c.save()
        signed = await asyncio.to_thread(sign_pdf, buf.getvalue())
        sig = PdfFileReader(BytesIO(signed)).embedded_signatures[0]
        assert "Test platform" in sig.signer_cert.subject.human_friendly
        assert b"ReportLab" in signed
        tampered = signed.replace(b"ReportLab", b"ReportLaX", 1)
        status = await async_validate_pdf_signature(
            PdfFileReader(BytesIO(tampered)).embedded_signatures[0]
        )
        assert not status.intact
    finally:
        reset_signer()

async def test_check_page(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, first_name="Алина")
    await _credited(db_session, user)
    code = (await client.get("/me/certificate", headers=dev(user))).json()["verifyCode"]
    root = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    async with root:
        resp = await root.get(f"/check/{code.lower().replace('-', '')}")
        assert resp.status_code == 200
        assert "Справка действительна" in resp.text and "Алина" in resp.text
        assert "1,5" in resp.text
        assert (await root.get("/check/AAA-AAA")).status_code == 404

        assert (await client.delete("/me", headers=dev(user))).status_code == 204
        resp = await root.get(f"/check/{code}")
        assert "Справка аннулирована" in resp.text and "Алина" not in resp.text

        for _ in range(30):
            await root.get("/check/AAA-AAA")
        assert (await root.get("/check/AAA-AAA")).status_code == 429

async def test_export_and_delete(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await _credited(db_session, user)
    db_session.add(MaxChat(user_id=user.id, chat_id=777))
    await db_session.commit()
    uid = user.id

    assert (await client.post("/me/export", headers=dev(user))).status_code == 204
    assert (await jobs(db_session, "notify.export"))[0].payload == {"user_id": str(uid)}

    org = await make_org(db_session)
    await add_member(db_session, org, user, role=OrgRole.OWNER)
    resp = await client.delete("/me", headers=dev(user))
    assert resp.status_code == 409 and resp.json() == {"code": "last_owner"}

    co = await make_user(db_session)
    await add_member(db_session, org, co, role=OrgRole.OWNER)
    await client.get("/me/certificate", headers=dev(user))
    assert (await client.delete("/me", headers=dev(user))).status_code == 204
    db_session.expunge_all()
    assert await db_session.get(User, uid) is None
    left = await db_session.scalar(
        select(func.count()).select_from(HourLedger).where(HourLedger.user_id == uid)
    )
    assert left == 0
    cert = await db_session.scalar(select(Certificate))
    assert cert is not None and cert.revoked_at is not None and cert.user_id is None
    assert (await jobs(db_session, "notify.profile_deleted"))[0].payload == {"chat_id": 777}

async def test_search_log_feeds_metrics(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    users = [await make_user(db_session) for _ in range(3)]
    params = {"duration_min": 60, "when": "tonight", "from": "campus"}
    for u in users:
        assert (await client.get("/search", headers=dev(u), params=params)).status_code == 200
    await client.get("/search/preview", headers=dev(users[0]), params=params)
    rows = (await db_session.scalars(select(SearchLog))).all()
    assert len(rows) == 3 and rows[0].window_from == msk(2026, 9, 29, 17, 30)
    view = await compute_metrics(db_session, NOW, None)
    assert view.funnel[0].value == 3
