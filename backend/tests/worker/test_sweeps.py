import os
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    BookingStatus,
    Category,
    LedgerSource,
    MicroAnswerStatus,
    NotifyMode,
    ShiftStatus,
    TransferStatus,
)
from app.db.models import (
    Booking,
    BusySlot,
    FreeWindow,
    HourLedger,
    Job,
    MicroAnswer,
    MicroTask,
    SeatTransfer,
    Shift,
)
from app.worker.jobs.sweeps import run_sweeps
from tests.bot.conftest import BotHarness, drain, now, with_chat
from tests.factories import make_org, make_user


async def test_finish_shift_credits_hours_and_marks_no_show(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    came = await make_user(db_session)
    manual = await make_user(db_session)
    absent = await make_user(db_session)
    chat = await with_chat(db_session, came)
    start = now() - timedelta(hours=3)
    shift = Shift(
        org_id=org.id,
        title="Субботник",
        category=Category.ECOLOGY,
        starts_at=start,
        ends_at=start + timedelta(minutes=100),
        capacity=5,
        checkin_secret=os.urandom(20),
    )
    db_session.add(shift)
    await db_session.flush()
    bookings = {
        came.id: Booking(shift_id=shift.id, user_id=came.id, status=BookingStatus.CHECKED_IN),
        manual.id: Booking(shift_id=shift.id, user_id=manual.id, status=BookingStatus.MANUAL),
        absent.id: Booking(shift_id=shift.id, user_id=absent.id, status=BookingStatus.GOING),
    }
    db_session.add_all(bookings.values())
    await db_session.commit()

    await run_sweeps(now())
    await run_sweeps(now() + timedelta(minutes=2))

    await db_session.refresh(shift)
    assert shift.status == ShiftStatus.FINISHED
    for booking in bookings.values():
        await db_session.refresh(booking)
    assert bookings[came.id].status == BookingStatus.DONE
    assert bookings[manual.id].status == BookingStatus.DONE
    assert bookings[absent.id].status == BookingStatus.NO_SHOW
    ledger = list(await db_session.scalars(select(HourLedger)))
    assert sorted(r.user_id for r in ledger) == sorted([came.id, manual.id])
    assert all(r.hours == Decimal("1.7") and r.source == LedgerSource.SHIFT for r in ledger)

    await drain()
    assert harness.transport.to_chat(chat)[0].text == (
        "Спасибо! «Субботник» засчитано: +1,7 ч в справку."
    )

async def test_expirations_pause_and_purge(harness: BotHarness, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    user.notify = NotifyMode.PAUSE
    user.pause_until = now() - timedelta(minutes=1)
    task = MicroTask(org_id=org.id, title="Т", text="…", minutes=10, answers_needed=1)
    db_session.add(task)
    await db_session.flush()
    answer = MicroAnswer(
        task_id=task.id,
        user_id=user.id,
        status=MicroAnswerStatus.TAKEN,
        deadline=now() - timedelta(minutes=1),
    )
    start = now() - timedelta(minutes=5)
    shift = Shift(
        org_id=org.id,
        title="Идёт",
        category=Category.PEOPLE,
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        capacity=3,
        checkin_secret=os.urandom(20),
    )
    db_session.add_all([answer, shift])
    await db_session.flush()
    booking = Booking(shift_id=shift.id, user_id=user.id)
    db_session.add(booking)
    await db_session.flush()
    transfer = SeatTransfer(booking_id=booking.id, token="tr1", expires_at=start)
    old = now() - timedelta(days=91)
    db_session.add_all(
        [
            transfer,
            FreeWindow(user_id=user.id, starts_at=old, ends_at=old + timedelta(hours=1)),
            FreeWindow(user_id=user.id, starts_at=now(), ends_at=now() + timedelta(hours=1)),
            BusySlot(user_id=user.id, starts_at=old, ends_at=old + timedelta(hours=1)),
        ]
    )
    await db_session.commit()

    await run_sweeps(now())

    for row in (answer, transfer, user, booking):
        await db_session.refresh(row)
    assert answer.status == MicroAnswerStatus.RELEASED
    assert transfer.status == TransferStatus.EXPIRED
    assert user.notify == NotifyMode.ALL and user.pause_until is None
    assert booking.status == BookingStatus.GOING
    assert await db_session.scalar(select(func.count()).select_from(FreeWindow)) == 1
    assert await db_session.scalar(select(func.count()).select_from(BusySlot)) == 0

async def test_weekly_pick_scheduled_once_and_cancelled(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    user.weekly_search = {"durationMin": 60, "when": "tonight", "from": "campus"}
    await db_session.commit()
    moment = now()

    await run_sweeps(moment)
    await run_sweeps(moment + timedelta(minutes=1))

    [job] = list(await db_session.scalars(select(Job).where(Job.kind == "notify.weekly_pick")))
    assert job.payload == {"user_id": str(user.id)}
    assert job.run_at == moment + timedelta(days=7)

    user.weekly_search = None
    await db_session.commit()
    await run_sweeps(moment + timedelta(minutes=2))
    await db_session.refresh(job)
    assert job.done_at is not None and job.last_error == "weekly_search_off"
