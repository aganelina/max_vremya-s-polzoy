from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas.base import CamelModel

OrgStatus = Literal["pending", "verified", "rejected"]

class OrgApplication(CamelModel):
    """Организация глазами её участника (GET /orgs/mine, ответ POST /orgs)."""

    id: str
    name: str
    status: OrgStatus
    reject_reason: str | None
    role: Literal["owner", "coordinator"]
    inn: str | None
    address: str
    district_id: str | None
    contact_name: str
    contact_phone: str
    sign_name: str | None
    sign_position: str | None
    has_seal: bool
    has_signature: bool
    created_at: AwareDatetime

class OperatorOrg(CamelModel):
    """Строка списка заявок оператора."""

    id: str
    name: str
    status: OrgStatus
    reject_reason: str | None
    inn: str | None
    address: str
    district_id: str | None
    contact_name: str
    contact_phone: str
    sign_name: str | None
    sign_position: str | None
    has_seal: bool
    has_signature: bool
    created_by_name: str | None
    created_at: AwareDatetime
    verified_at: AwareDatetime | None

class VerifyIn(CamelModel):
    """Проверка заявки: точка фактического адреса (для дороги от корпуса) и район."""

    lat: float
    lon: float
    district_id: str | None = None

class RejectIn(CamelModel):
    reason: str = Field(min_length=1, max_length=500)
