import json
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.transport import MaxApiError, MaxRetryableError
from app.config import get_settings
from app.db.enums import (
    BookingStatus,
    CertPeriod,
    HelpStatus,
    MicroAnswerStatus,
    NotifyMode,
    OrgRole,
    OrgStatus,
    ShiftPlace,
    ShiftStatus,
)
from app.db.models import (
    Booking,
    Certificate,
    Company,
    FreeWindow,
    HelpRequest,
    Job,
    MentorRequest,
    MicroAnswer,
    MicroTask,
    Schedule,
    User,
)
from app.worker.jobs import notifications
from app.worker.queue import enqueue
from tests.bot.conftest import BotHarness, drain, make_shift, now, with_chat
from tests.factories import add_member, make_org, make_user


async def _user(db_session: AsyncSession, notify: NotifyMode = NotifyMode.ALL, name: str = "Алина"):
    user = await make_user(db_session, first_name=name)
    user.notify = notify
    if notify is NotifyMode.PAUSE:
        user.pause_until = now() + timedelta(days=3)
    await db_session.commit()
    return user, await with_chat(db_session, user)

async def _run(db_session: AsyncSession, kind: str, payload: dict[str, object]) -> None:
    await enqueue(db_session, kind, payload)
    await db_session.commit()
    await drain()

async def test_instructions(harness: BotHarness, db_session: AsyncSession) -> None:
    user, chat = await _user(db_session, NotifyMode.MINE)
    shift = await make_shift(db_session, await make_org(db_session))
    booking = Booking(shift_id=shift.id, user_id=user.id)
    db_session.add(booking)
    await db_session.commit()

    await _run(db_session, "notify.instructions", {"booking_id": str(booking.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat
    assert "Разбор книг" in (sent.text or "") and "Возьми перчатки" in (sent.text or "")

async def test_shift_cancelled_is_critical_even_on_pause(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    paused, paused_chat = await _user(db_session, NotifyMode.PAUSE)
    other, other_chat = await _user(db_session)
    shift = await make_shift(db_session, await make_org(db_session))
    shift.status = ShiftStatus.CANCELLED
    await db_session.commit()

    await _run(
        db_session,
        "notify.shift_cancelled",
        {"shift_id": str(shift.id), "user_ids": [str(paused.id), str(other.id)]},
    )

    assert {m.chat_id for m in harness.transport.sent} == {paused_chat, other_chat}
    assert all("отменена" in t for t in harness.transport.texts)

async def test_shift_cancelled_without_list_uses_bookings(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat = await _user(db_session)
    early, early_chat = await _user(db_session)
    shift = await make_shift(db_session, await make_org(db_session))
    db_session.add_all(
        [
            Booking(
                shift_id=shift.id,
                user_id=user.id,
                status=BookingStatus.CANCELLED,
                cancelled_at=now(),
            ),
            Booking(
                shift_id=shift.id,
                user_id=early.id,
                status=BookingStatus.CANCELLED,
                cancelled_at=now() - timedelta(days=1),
            ),
        ]
    )
    await db_session.commit()

    await _run(db_session, "notify.shift_cancelled", {"shift_id": str(shift.id)})

    assert [m.chat_id for m in harness.transport.sent] == [chat]
    assert harness.transport.to_chat(early_chat) == []

async def test_micro_reviewed(harness: BotHarness, db_session: AsyncSession) -> None:
    user, _ = await _user(db_session, NotifyMode.MINE)
    org = await make_org(db_session)
    task = MicroTask(org_id=org.id, title="Перевести текст", text="…", minutes=30, answers_needed=3)
    db_session.add(task)
    await db_session.flush()
    answer = MicroAnswer(
        task_id=task.id, user_id=user.id, status=MicroAnswerStatus.RETURNED, review_note="Короче"
    )
    db_session.add(answer)
    await db_session.commit()

    await _run(db_session, "notify.micro_reviewed", {"answer_id": str(answer.id)})

    assert harness.transport.texts == ["Микро-дело «Перевести текст» вернули на доработку: Короче"]

async def test_bank_response(harness: BotHarness, db_session: AsyncSession) -> None:
    author, chat = await _user(db_session)
    helper, _ = await _user(db_session, name="Тимур")
    request = HelpRequest(
        author_id=author.id, text="Помочь с переездом", hours=Decimal("1.0"), status=HelpStatus.OPEN
    )
    db_session.add(request)
    await db_session.commit()

    await _run(
        db_session,
        "notify.bank_response",
        {"request_id": str(request.id), "helper_id": str(helper.id)},
    )

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and (sent.text or "").startswith("Тимур готов помочь")

async def test_company_remind(harness: BotHarness, db_session: AsyncSession) -> None:
    owner, _ = await _user(db_session, name="Ира")
    member, chat = await _user(db_session)
    company = Company(owner_id=owner.id, token="cotok", date=now().date())
    db_session.add(company)
    await db_session.commit()

    await _run(
        db_session,
        "notify.company_remind",
        {"company_id": str(company.id), "member_user_id": str(member.id)},
    )

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and (sent.text or "").startswith("Ира зовёт тебя")

async def test_mentor_request(harness: BotHarness, db_session: AsyncSession) -> None:
    mentor, chat = await _user(db_session)
    newbie, _ = await _user(db_session, name="Петя")
    shift = await make_shift(db_session, await make_org(db_session))
    request = MentorRequest(newbie_id=newbie.id, shift_id=shift.id, mentor_id=mentor.id)
    db_session.add(request)
    await db_session.commit()

    await _run(db_session, "notify.mentor_request", {"request_id": str(request.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and "Петя впервые" in (sent.text or "")

async def test_org_review(harness: BotHarness, db_session: AsyncSession) -> None:
    owner, chat = await _user(db_session)
    org = await make_org(db_session, status=OrgStatus.REJECTED)
    org.reject_reason = "нет ИНН"
    await db_session.commit()
    await add_member(db_session, org, owner, role=OrgRole.OWNER)

    await _run(db_session, "notify.org_review", {"org_id": str(org.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and "отклонена: нет ИНН" in (sent.text or "")

async def test_export_sends_json_file(harness: BotHarness, db_session: AsyncSession) -> None:
    user, chat = await _user(db_session, NotifyMode.PAUSE)
    shift = await make_shift(db_session, await make_org(db_session))
    db_session.add(Booking(shift_id=shift.id, user_id=user.id))
    await db_session.commit()

    await _run(db_session, "notify.export", {"user_id": str(user.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and sent.filename == "vremya-export.json"
    data = json.loads(sent.file or b"")
    assert data["profile"]["id"] == str(user.id)
    assert len(data["bookings"]) == 1

async def test_certificate_sends_pdf(
    harness: BotHarness, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_pdf(session: AsyncSession, cert: Certificate) -> bytes:
        return b"%PDF-1.4 stub"

    monkeypatch.setattr(notifications, "certificate_pdf", fake_pdf)
    user, chat = await _user(db_session)
    cert = Certificate(
        user_id=user.id, code="ABC-DEF", period=CertPeriod.ALL, rows=[], total=Decimal("3.5")
    )
    db_session.add(cert)
    await db_session.commit()

    await _run(db_session, "notify.certificate", {"certificate_id": str(cert.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat
    assert sent.filename == "spravka-ABC-DEF.pdf" and sent.file == b"%PDF-1.4 stub"

async def test_profile_deleted(harness: BotHarness, db_session: AsyncSession) -> None:
    await _run(db_session, "notify.profile_deleted", {"chat_id": 555})
    [sent] = harness.transport.sent
    assert sent.chat_id == 555 and (sent.text or "").startswith("Профиль удалён")

async def test_weekly_pick(harness: BotHarness, db_session: AsyncSession) -> None:
    user, chat = await _user(db_session)
    user.weekly_search = {"durationMin": 60, "when": "tomorrow", "from": "campus"}
    await db_session.commit()
    org = await make_org(db_session)
    tz = get_settings().tz
    for day in (1, 2, 3, 4):
        date = (now().astimezone(tz) + timedelta(days=day)).date()
        shift = await make_shift(
            db_session,
            org,
            starts_at=datetime.combine(date, time(17, 40), tzinfo=tz),
            minutes=30,
            title=f"Дело {day}",
        )
        shift.place = ShiftPlace.ONLINE
    await db_session.commit()

    await _run(db_session, "notify.weekly_pick", {"user_id": str(user.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat
    assert "Дело 1" in (sent.text or "") and "Дело 4" not in (sent.text or "")

async def test_shift_offer_to_fitting_windows_and_notify_all(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    fits, fits_chat = await _user(db_session)
    mine, _ = await _user(db_session, NotifyMode.MINE)
    busy, _ = await _user(db_session)
    shift = await make_shift(db_session, await make_org(db_session))
    for user in (fits, mine):
        db_session.add(
            FreeWindow(
                user_id=user.id,
                starts_at=shift.starts_at - timedelta(hours=1),
                ends_at=shift.ends_at + timedelta(hours=1),
            )
        )
    db_session.add(FreeWindow(user_id=busy.id, starts_at=shift.starts_at, ends_at=shift.starts_at))
    await db_session.commit()

    await _run(db_session, "shift.offer", {"shift_id": str(shift.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == fits_chat

async def test_pause_blocks_non_critical(harness: BotHarness, db_session: AsyncSession) -> None:
    user, _ = await _user(db_session, NotifyMode.PAUSE)
    shift = await make_shift(db_session, await make_org(db_session))
    booking = Booking(shift_id=shift.id, user_id=user.id)
    db_session.add(booking)
    await db_session.commit()

    await _run(db_session, "notify.instructions", {"booking_id": str(booking.id)})

    assert harness.transport.sent == []

async def test_retryable_error_is_retried_later(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    harness.transport.failures.append(MaxRetryableError(429, "too.many.requests"))
    await _run(db_session, "notify.profile_deleted", {"chat_id": 556})

    job = (await db_session.scalars(select(Job))).one()
    assert job.done_at is None and job.attempts == 1
    assert job.last_error == "MaxRetryableError"
    assert job.run_at > now()

async def test_permanent_error_is_not_retried(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    harness.transport.failures.append(MaxApiError(403, "chat.denied"))
    await _run(db_session, "notify.profile_deleted", {"chat_id": 557})

    job = (await db_session.scalars(select(Job))).one()
    assert job.done_at is not None and job.attempts == 0

async def test_user_without_chat_is_messaged_by_user_id(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    await _run(db_session, "notify.export", {"user_id": str(user.id)})
    [sent] = harness.transport.sent
    assert sent.chat_id is None and sent.user_id == user.max_user_id
    assert isinstance(user, User)

async def test_certificate_with_real_generator(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat = await _user(db_session)
    cert = Certificate(
        user_id=user.id, code="XYZ-QRS", period=CertPeriod.ALL, rows=[], total=Decimal("0")
    )
    db_session.add(cert)
    await db_session.commit()

    await _run(db_session, "notify.certificate", {"certificate_id": str(cert.id)})

    [sent] = harness.transport.sent
    assert sent.chat_id == chat and (sent.file or b"").startswith(b"%PDF")

async def test_weekly_pick_uses_saved_window(harness: BotHarness, db_session: AsyncSession) -> None:
    user, _ = await _user(db_session)
    user.weekly_search = {"durationMin": 120, "when": "tomorrow", "from": "campus"}
    org = await make_org(db_session)
    tz = get_settings().tz
    tomorrow = (now().astimezone(tz) + timedelta(days=1)).date()
    window_start = datetime.combine(tomorrow, time(18, 0), tzinfo=tz)
    db_session.add(Schedule(user_id=user.id, file_name="rasp.ics", uploaded_at=now()))
    db_session.add(
        FreeWindow(
            user_id=user.id, starts_at=window_start, ends_at=window_start + timedelta(hours=3)
        )
    )
    fits = await make_shift(
        db_session, org, starts_at=window_start + timedelta(minutes=30), minutes=60, title="Влезает"
    )
    late = await make_shift(
        db_session, org, starts_at=window_start + timedelta(hours=5), minutes=60, title="Поздно"
    )
    for shift in (fits, late):
        shift.place = ShiftPlace.ONLINE
    await db_session.commit()

    picked = await notifications.pick_for_week(db_session, user)

    assert [s.title for s in picked] == ["Влезает"]

async def test_weekly_pick_empty_when_schedule_has_no_window(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, _ = await _user(db_session)
    user.weekly_search = {"durationMin": 120, "when": "tomorrow", "from": "campus"}
    db_session.add(Schedule(user_id=user.id, file_name="rasp.ics", uploaded_at=now()))
    shift = await make_shift(db_session, await make_org(db_session), title="Поверх пар")
    shift.place = ShiftPlace.ONLINE
    await db_session.commit()

    assert await notifications.pick_for_week(db_session, user) == []
