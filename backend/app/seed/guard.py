import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Booking, User
from app.seed.ids import DEMO_MAX_USER_ID


def demo_max_ids() -> set[int]:
    from app.seed import coord, deals, engagement

    ids = {DEMO_MAX_USER_ID}
    for people in (coord.PEOPLE, deals.PEOPLE, engagement.PEOPLE):
        ids.update(int(person[2]) for person in people)
    return ids

async def has_real_bookings(session: AsyncSession, shift_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(Booking.id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.shift_id == shift_id, User.max_user_id.not_in(demo_max_ids()))
        .limit(1)
    )
    return found is not None
