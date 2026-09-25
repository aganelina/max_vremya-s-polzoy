import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, HelpStatus
from app.db.models import Booking, HelpRequest, MicroTask, Org, Shift, User


async def make_task(
    session: AsyncSession,
    org: Org,
    *,
    title: str = "Задание",
    answers_needed: int = 5,
    created_at: datetime | None = None,
    active: bool = True,
) -> MicroTask:
    task = MicroTask(
        org_id=org.id,
        title=title,
        text="Что сделать",
        minutes=15,
        answers_needed=answers_needed,
        active=active,
    )
    if created_at is not None:
        task.created_at = created_at
    session.add(task)
    await session.commit()
    return task

async def make_request(
    session: AsyncSession,
    author: User,
    *,
    hours: str = "1",
    status: HelpStatus = HelpStatus.OPEN,
    helper: User | None = None,
    district: str = "vakh",
) -> HelpRequest:
    request = HelpRequest(
        author_id=author.id,
        text="Помочь с переездом",
        hours=Decimal(hours),
        when_label="суббота",
        district_id=district,
        status=status,
        helper_id=helper.id if helper else None,
    )
    session.add(request)
    await session.commit()
    return request

async def make_shift(
    session: AsyncSession,
    org: Org,
    starts_at: datetime,
    *,
    minutes: int = 60,
    capacity: int = 5,
    category: Category = Category.PEOPLE,
) -> Shift:
    shift = Shift(
        org_id=org.id,
        title="Смена",
        category=category,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        capacity=capacity,
        address="ул. Тестовая, 1",
        checkin_secret=os.urandom(20),
    )
    session.add(shift)
    await session.commit()
    return shift

async def book(
    session: AsyncSession, shift: Shift, user: User, status: BookingStatus = BookingStatus.GOING
) -> Booking:
    booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
    session.add(booking)
    await session.commit()
    return booking
