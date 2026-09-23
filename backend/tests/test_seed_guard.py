from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.db.enums import BookingStatus
from app.db.models import Booking, Shift
from app.seed import seed_demo
from app.seed.ids import demo_id
from tests.conftest import NOW
from tests.factories import make_user


async def test_refresh_keeps_shifts_with_real_bookings(db_session: AsyncSession) -> None:
    async with db.transaction() as session:
        await seed_demo(session, NOW)

    real = await make_user(db_session, first_name="Настоящий")
    touched: dict[str, object] = {}
    for key in ("s-books", "d-sort", "r-letters"):
        shift = await db_session.get(Shift, demo_id(key))
        if shift is None:
            continue
        db_session.add(Booking(shift_id=shift.id, user_id=real.id, status=BookingStatus.GOING))
        touched[key] = shift.starts_at
    free = await db_session.get(Shift, demo_id("d-park"))
    assert free is not None
    free_before = free.starts_at
    await db_session.commit()
    assert "s-books" in touched and "d-sort" in touched

    async with db.transaction() as session:
        await seed_demo(session, NOW + timedelta(days=1))

    db_session.expunge_all()
    for key, starts_at in touched.items():
        shift = await db_session.get(Shift, demo_id(key))
        assert shift is not None and shift.starts_at == starts_at, key
    moved = await db_session.get(Shift, demo_id("d-park"))
    assert moved is not None and moved.starts_at == free_before + timedelta(days=1)
