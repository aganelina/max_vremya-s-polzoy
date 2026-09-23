from fastapi import APIRouter
from sqlalchemy import select

from app.api.schemas.common import Dict
from app.api.schemas.dictionaries import Dictionaries
from app.auth.deps import CurrentUser, DbSession
from app.db.models import District, University

router = APIRouter(tags=["profile"])

@router.get("/dictionaries", response_model=Dictionaries)
async def get_dictionaries(_: CurrentUser, session: DbSession) -> Dictionaries:
    universities = await session.scalars(
        select(University).order_by(University.position, University.name)
    )
    districts = await session.scalars(select(District).order_by(District.position, District.name))
    return Dictionaries(
        universities=[Dict(id=u.id, name=u.name) for u in universities],
        districts=[Dict(id=d.id, name=d.name) for d in districts],
    )
