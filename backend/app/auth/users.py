from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def upsert_user(session: AsyncSession, max_user_id: int, first_name: str | None) -> User:
    by_max_id = select(User).where(User.max_user_id == max_user_id)
    user = await session.scalar(by_max_id)
    if user is None:
        await session.execute(
            pg_insert(User)
            .values(max_user_id=max_user_id, first_name=first_name or "")
            .on_conflict_do_nothing(index_elements=[User.max_user_id])
        )
        user = (await session.scalars(by_max_id)).one()
    if first_name and user.first_name != first_name:
        user.first_name = first_name
    return user
