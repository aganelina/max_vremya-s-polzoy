from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, OrgStatus, ShiftPlace, ShiftStatus
from app.db.models import Booking, Job, Org, Shift, User
from app.domain.checkin_code import new_secret

MSK = ZoneInfo("Europe/Moscow")
NEAR = (55.7899, 49.1150)

def msk(*args: int) -> datetime:
    return datetime(*args, tzinfo=MSK)  # type: ignore[misc]

async def make_org(
    session: AsyncSession, name: str = "Книжный мост", status: OrgStatus = OrgStatus.VERIFIED
) -> Org:
    org = Org(
        name=name,
        contact_name="Гульнара",
        contact_phone="+70000000000",
        address="ул. Баумана, 19",
        lat=NEAR[0],
        lon=NEAR[1],
        district_id="vakh",
        status=status,
        sign_name="Г. Р. Сафина",
        sign_position="координатор",
    )
    session.add(org)
    await session.commit()
    return org

async def make_shift(
    session: AsyncSession,
    org: Org,
    start: datetime,
    minutes: int = 60,
    *,
    capacity: int = 5,
    category: Category = Category.BOOKS,
    title: str = "Разбор книг",
    place: ShiftPlace = ShiftPlace.ORG,
    district_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    status: ShiftStatus = ShiftStatus.OPEN,
) -> Shift:
    shift = Shift(
        org_id=org.id,
        title=title,
        description="Разобрать книги",
        category=category,
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        capacity=capacity,
        place=place,
        address="ул. Баумана, 19",
        address_note="вход со двора",
        district_id=district_id,
        lat=lat,
        lon=lon,
        instructions="Спросить Гульнару",
        impact="3 коробки книг",
        status=status,
        checkin_secret=new_secret(),
    )
    session.add(shift)
    await session.commit()
    return shift

async def book(
    session: AsyncSession,
    shift: Shift,
    user: User,
    status: BookingStatus = BookingStatus.GOING,
    created_at: datetime | None = None,
) -> Booking:
    booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
    if created_at is not None:
        booking.created_at = created_at
    session.add(booking)
    await session.commit()
    return booking

async def jobs(session: AsyncSession, kind: str) -> list[Job]:
    q = select(Job).where(Job.kind == kind).execution_options(populate_existing=True)
    return list((await session.scalars(q)).all())
