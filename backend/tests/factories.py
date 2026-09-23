import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, LedgerSource, OrgRole, OrgStatus
from app.db.models import Booking, HourLedger, Org, OrgMember, Shift, User

_max_ids = count(1000)

async def make_user(
    session: AsyncSession,
    *,
    onboarded: bool = True,
    first_name: str = "Тест",
    is_operator: bool = False,
    at: datetime | None = None,
) -> User:
    at = at or datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    user = User(
        max_user_id=next(_max_ids),
        first_name=first_name,
        is_operator=is_operator,
        consent_at=at if onboarded else None,
        onboarded_at=at if onboarded else None,
        university_id="kfu" if onboarded else None,
        district_id="vakh" if onboarded else None,
    )
    session.add(user)
    await session.commit()
    return user

async def make_org(session: AsyncSession, *, status: OrgStatus = OrgStatus.VERIFIED) -> Org:
    org = Org(
        name="Тестовая организация",
        contact_name="Контакт",
        contact_phone="+70000000000",
        address="ул. Тестовая, 1",
        status=status,
    )
    session.add(org)
    await session.commit()
    return org

async def add_member(
    session: AsyncSession,
    org: Org,
    user: User,
    *,
    role: OrgRole = OrgRole.COORDINATOR,
    revoked_at: datetime | None = None,
) -> None:
    session.add(OrgMember(org_id=org.id, user_id=user.id, role=role, revoked_at=revoked_at))
    await session.commit()

async def credit(
    session: AsyncSession,
    user: User,
    hours: str,
    at: datetime,
    source: LedgerSource = LedgerSource.SHIFT,
) -> None:
    session.add(HourLedger(user_id=user.id, source=source, hours=Decimal(hours), accepted_at=at))
    await session.commit()

async def done_booking(session: AsyncSession, org: Org, user: User, at: datetime) -> None:
    shift = Shift(
        org_id=org.id,
        title="Смена",
        category=Category.PEOPLE,
        starts_at=at,
        ends_at=at + timedelta(hours=1),
        capacity=5,
        checkin_secret=os.urandom(20),
    )
    session.add(shift)
    await session.flush()
    session.add(Booking(shift_id=shift.id, user_id=user.id, status=BookingStatus.DONE))
    await session.commit()
