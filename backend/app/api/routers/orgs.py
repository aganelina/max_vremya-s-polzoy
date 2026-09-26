import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFound
from app.api.schemas.coord import Metrics
from app.api.schemas.orgs import OperatorOrg, OrgApplication, RejectIn, VerifyIn
from app.api.schemas.orgs import OrgStatus as OrgStatusLiteral
from app.auth.deps import DbSession, Now, OnboardedUser, Operator
from app.db.enums import OrgRole, OrgStatus, ShiftPlace
from app.db.models import District, Org, OrgMember, Shift, User
from app.domain.coord import CoordError
from app.domain.metrics import compute_metrics
from app.domain.orgs import MAX_IMAGE_BYTES, check_png, clean_inn, clean_phone, clean_text
from app.worker.queue import enqueue

router = APIRouter(tags=["orgs"])
operator_router = APIRouter(prefix="/operator", tags=["operator"])

def _application(org: Org, role: OrgRole) -> OrgApplication:
    return OrgApplication(
        id=str(org.id),
        name=org.name,
        status=org.status.value,
        reject_reason=org.reject_reason,
        role=role.value,
        inn=org.inn,
        address=org.address,
        district_id=org.district_id,
        contact_name=org.contact_name,
        contact_phone=org.contact_phone,
        sign_name=org.sign_name,
        sign_position=org.sign_position,
        has_seal=org.seal_image is not None,
        has_signature=org.signature_image is not None,
        created_at=org.created_at,
    )

async def _image(upload: UploadFile | None, field: str) -> bytes | None:
    if upload is None or not upload.filename:
        return None
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    return check_png(data, field) if data else None

FormStr = Annotated[str, Form()]
FormOptStr = Annotated[str | None, Form()]

@router.post("/orgs", response_model=OrgApplication)
async def apply_org(
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    name: FormStr,
    address: FormStr,
    contact_name: Annotated[str, Form(alias="contactName")],
    contact_phone: Annotated[str, Form(alias="contactPhone")],
    inn: FormOptStr = None,
    district_id: Annotated[str | None, Form(alias="districtId")] = None,
    sign_name: Annotated[str | None, Form(alias="signName")] = None,
    sign_position: Annotated[str | None, Form(alias="signPosition")] = None,
    seal: Annotated[UploadFile | None, File()] = None,
    signature: Annotated[UploadFile | None, File()] = None,
) -> OrgApplication:
    pending = await session.scalar(
        select(Org.id)
        .join(OrgMember, OrgMember.org_id == Org.id)
        .where(
            OrgMember.user_id == user.id,
            OrgMember.role == OrgRole.OWNER,
            Org.status == OrgStatus.PENDING,
        )
        .limit(1)
    )
    if pending is not None:
        raise CoordError(409, "application_pending")
    if district_id and await session.get(District, district_id) is None:
        raise CoordError(422, "unknown_district")
    org = Org(
        name=clean_text(name, "invalid_name", required=True),
        inn=clean_inn(inn),
        address=clean_text(address, "invalid_address", required=True, max_len=300),
        district_id=district_id or None,
        contact_name=clean_text(contact_name, "invalid_contact_name", required=True),
        contact_phone=clean_phone(contact_phone),
        sign_name=clean_text(sign_name, "invalid_sign_name", required=False) or None,
        sign_position=clean_text(sign_position, "invalid_sign_position", required=False) or None,
        seal_image=await _image(seal, "seal"),
        signature_image=await _image(signature, "signature"),
        status=OrgStatus.PENDING,
        created_by=user.id,
        created_at=now,
    )
    session.add(org)
    await session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role=OrgRole.OWNER, created_at=now))
    await session.commit()
    return _application(org, OrgRole.OWNER)

@router.get("/orgs/mine", response_model=list[OrgApplication])
async def my_orgs(user: OnboardedUser, session: DbSession) -> list[OrgApplication]:
    rows = await session.execute(
        select(Org, OrgMember.role)
        .join(OrgMember, OrgMember.org_id == Org.id)
        .where(OrgMember.user_id == user.id, OrgMember.revoked_at.is_(None))
        .order_by(Org.created_at.desc(), Org.id)
    )
    return [_application(org, role) for org, role in rows]

async def _org_or_404(session: AsyncSession, org_id: str, *, lock: bool = False) -> Org:
    try:
        key = uuid.UUID(org_id)
    except ValueError:
        raise NotFound("org_not_found") from None
    stmt = select(Org).where(Org.id == key)
    if lock:
        stmt = stmt.with_for_update()
    org = await session.scalar(stmt)
    if org is None:
        raise NotFound("org_not_found")
    return org

def _operator_view(org: Org, author: str | None) -> OperatorOrg:
    return OperatorOrg(
        id=str(org.id),
        name=org.name,
        status=org.status.value,
        reject_reason=org.reject_reason,
        inn=org.inn,
        address=org.address,
        district_id=org.district_id,
        contact_name=org.contact_name,
        contact_phone=org.contact_phone,
        sign_name=org.sign_name,
        sign_position=org.sign_position,
        has_seal=org.seal_image is not None,
        has_signature=org.signature_image is not None,
        created_by_name=author,
        created_at=org.created_at,
        verified_at=org.verified_at,
    )

@operator_router.get("/orgs", response_model=list[OperatorOrg])
async def operator_orgs(
    _: Operator, session: DbSession, status: OrgStatusLiteral | None = None
) -> list[OperatorOrg]:
    stmt = select(Org, User.first_name).outerjoin(User, User.id == Org.created_by)
    if status is not None:
        stmt = stmt.where(Org.status == OrgStatus(status))
    rows = await session.execute(stmt.order_by(Org.created_at, Org.id))
    return [_operator_view(org, author) for org, author in rows]

@operator_router.get("/orgs/{org_id}/{kind}.png")
async def operator_org_image(org_id: str, kind: str, _: Operator, session: DbSession) -> Response:
    """Изображение печати или подписи из заявки — оператору для проверки."""
    org = await _org_or_404(session, org_id)
    data = {"seal": org.seal_image, "signature": org.signature_image}.get(kind)
    if data is None:
        raise NotFound("image_not_found")
    return Response(content=data, media_type="image/png")

RU_LAT = (41.0, 82.0)
RU_LON = (19.0, 180.0)

@operator_router.post("/orgs/{org_id}/verify", response_model=OperatorOrg)
async def verify_org(
    org_id: str, body: VerifyIn, operator: Operator, session: DbSession, now: Now
) -> OperatorOrg:
    """Подтверждение с точкой адреса: без неё дорогу от корпуса не оценить.
    Точку получают и уже созданные смены организации без своей точки."""
    org = await _org_or_404(session, org_id, lock=True)
    if org.status is not OrgStatus.PENDING:
        raise CoordError(409, "not_pending")
    if not (RU_LAT[0] <= body.lat <= RU_LAT[1] and RU_LON[0] <= body.lon <= RU_LON[1]):
        raise CoordError(422, "invalid_point")
    if body.district_id and await session.get(District, body.district_id) is None:
        raise CoordError(422, "unknown_district")
    org.lat, org.lon = body.lat, body.lon
    if body.district_id:
        org.district_id = body.district_id
    await session.execute(
        update(Shift)
        .where(
            Shift.org_id == org.id,
            Shift.place != ShiftPlace.ONLINE,
            or_(Shift.lat.is_(None), Shift.lon.is_(None)),
        )
        .values(lat=body.lat, lon=body.lon)
    )
    org.status = OrgStatus.VERIFIED
    org.verified_at = now
    org.verified_by = operator.id
    org.reject_reason = None
    await enqueue(session, "notify.org_review", {"org_id": str(org.id)})
    await session.commit()
    return _operator_view(org, None)

@operator_router.post("/orgs/{org_id}/reject", response_model=OperatorOrg)
async def reject_org(org_id: str, body: RejectIn, _: Operator, session: DbSession) -> OperatorOrg:
    org = await _org_or_404(session, org_id, lock=True)
    if org.status is not OrgStatus.PENDING:
        raise CoordError(409, "not_pending")
    reason = body.reason.strip()
    if not reason:
        raise CoordError(422, "reason_required")
    org.status = OrgStatus.REJECTED
    org.reject_reason = reason
    await enqueue(session, "notify.org_review", {"org_id": str(org.id)})
    await session.commit()
    return _operator_view(org, None)

@operator_router.get("/metrics", response_model=Metrics)
async def operator_metrics(_: Operator, session: DbSession, now: Now) -> Metrics:
    """Метрики пилота с полным списком организаций — только оператору."""
    return Metrics.model_validate(await compute_metrics(session, now, own_org_id=None))
