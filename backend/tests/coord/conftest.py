import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, OrgRole, ShiftStatus
from app.db.models import Booking, Org, Shift, User
from tests.conftest import NOW
from tests.factories import add_member, make_org, make_user


@dataclass
class Team:
    owner: User
    org: Org

@pytest_asyncio.fixture
async def team(db_session: AsyncSession) -> Team:
    owner = await make_user(db_session, first_name="Гульнара")
    org = await make_org(db_session)
    org.district_id = "vakh"
    org.lat, org.lon = 55.7899, 49.1150
    await db_session.commit()
    await add_member(db_session, org, owner, role=OrgRole.OWNER)
    return Team(owner=owner, org=org)

async def make_shift(
    session: AsyncSession,
    org: Org,
    *,
    starts_at: datetime | None = None,
    minutes: int = 90,
    capacity: int = 8,
    status: ShiftStatus = ShiftStatus.OPEN,
    title: str = "Разбор книг",
) -> Shift:
    starts_at = starts_at or NOW + timedelta(days=1)
    shift = Shift(
        org_id=org.id,
        title=title,
        category=Category.BOOKS,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        capacity=capacity,
        address=org.address,
        status=status,
        checkin_secret=os.urandom(20),
    )
    session.add(shift)
    await session.commit()
    return shift

async def book(
    session: AsyncSession,
    shift: Shift,
    user: User,
    status: BookingStatus = BookingStatus.GOING,
    checked_in_at: datetime | None = None,
) -> Booking:
    booking = Booking(
        shift_id=shift.id, user_id=user.id, status=status, checked_in_at=checked_in_at
    )
    session.add(booking)
    await session.commit()
    return booking
