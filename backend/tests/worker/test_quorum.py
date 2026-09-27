from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, ShiftStatus, TransferStatus
from app.db.models import Booking, HourLedger, Job, SeatTransfer, Shift
from app.worker.jobs.sweeps import run_sweeps
from tests.bot.conftest import BotHarness, drain, now, with_chat
from tests.factories import make_org, make_user


@pytest.mark.parametrize("delay", [timedelta(), timedelta(days=1)])
async def test_missing_quorum_cancels_once_without_penalty(
    harness: BotHarness,
    db_session: AsyncSession,
    delay: timedelta,
) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    chat = await with_chat(db_session, user)
    start = now()
    shift = Shift(
        org_id=org.id,
        title="Команда",
        category=Category.PEOPLE,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        capacity=2,
        quorum=True,
        checkin_secret=b"quorum-test",
        created_by=user.id,
    )
    db_session.add(shift)
    await db_session.flush()
    booking = Booking(
        shift_id=shift.id,
        user_id=user.id,
        status=BookingStatus.CHECKED_IN,
        created_at=start - timedelta(hours=1),
    )
    db_session.add(booking)
    await db_session.flush()
    transfer = SeatTransfer(
        booking_id=booking.id,
        token="quorum-test",
        expires_at=start,
        status=TransferStatus.OPEN,
    )
    db_session.add(transfer)
    await db_session.commit()
    await run_sweeps(start - timedelta(seconds=1))
    await db_session.refresh(shift)
    assert shift.status == ShiftStatus.OPEN
    await run_sweeps(start + delay)
    await run_sweeps(start + delay + timedelta(minutes=2))
    for item in (shift, booking, transfer):
        await db_session.refresh(item)
    assert shift.status == ShiftStatus.CANCELLED
    assert booking.status == BookingStatus.CANCELLED
    assert transfer.status == TransferStatus.EXPIRED
    assert await db_session.scalar(select(func.count()).select_from(HourLedger)) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.kind == "notify.shift_cancelled",
            )
        )
        == 1
    )
    await drain()
    messages = harness.transport.to_chat(chat)
    assert len(messages) == 1
    assert "не набрала команду" in messages[0].text

async def test_quorum_uses_bookings_at_start_and_stays_confirmed(
    harness: BotHarness,
    db_session: AsyncSession,
) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    start = now()
    shift = Shift(
        org_id=org.id,
        title="Команда",
        category=Category.PEOPLE,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        capacity=1,
        quorum=True,
        checkin_secret=b"quorum-test",
    )
    db_session.add(shift)
    await db_session.flush()
    booking = Booking(
        shift_id=shift.id,
        user_id=user.id,
        status=BookingStatus.CANCELLED,
        created_at=start - timedelta(hours=1),
        cancelled_at=start + timedelta(minutes=1),
    )
    db_session.add(booking)
    await db_session.commit()
    await run_sweeps(start + timedelta(minutes=2))
    await db_session.refresh(shift)
    assert shift.status == ShiftStatus.OPEN
    assert shift.quorum_confirmed_at == start
    await run_sweeps(start + timedelta(hours=2))
    await db_session.refresh(shift)
    assert shift.status == ShiftStatus.FINISHED

async def test_cancelled_before_start_does_not_fill_quorum(
    harness: BotHarness,
    db_session: AsyncSession,
) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    shift = Shift(
        org_id=org.id,
        title="Команда",
        category=Category.PEOPLE,
        starts_at=now(),
        ends_at=now() + timedelta(hours=1),
        capacity=1,
        quorum=True,
        checkin_secret=b"quorum-test",
    )
    db_session.add(shift)
    await db_session.flush()
    db_session.add(
        Booking(
            shift_id=shift.id,
            user_id=user.id,
            status=BookingStatus.CANCELLED,
            created_at=now() - timedelta(hours=1),
            cancelled_at=now() - timedelta(seconds=1),
        )
    )
    await db_session.commit()
    await run_sweeps(now())
    await db_session.refresh(shift)
    assert shift.status == ShiftStatus.CANCELLED
