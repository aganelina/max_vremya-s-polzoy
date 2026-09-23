from fastapi import APIRouter, Response

from app.api.errors import Conflict
from app.auth.deps import CurrentUser, DbSession, Now
from app.domain.account import erase_user, sole_owned_orgs
from app.worker.queue import enqueue

router = APIRouter(tags=["account"])

@router.post("/me/export", status_code=204)
async def export_data(user: CurrentUser, session: DbSession) -> Response:
    await enqueue(session, "notify.export", {"user_id": str(user.id)})
    await session.commit()
    return Response(status_code=204)

@router.delete("/me", status_code=204)
async def delete_profile(user: CurrentUser, session: DbSession, now: Now) -> Response:
    if await sole_owned_orgs(session, user.id):
        raise Conflict("last_owner")
    chat_id = await erase_user(session, user, now)
    if chat_id is not None:
        await enqueue(session, "notify.profile_deleted", {"chat_id": chat_id})
    await session.commit()
    return Response(status_code=204)
