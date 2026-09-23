from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from app.api.schemas.base import CamelModel, Optional
from app.api.schemas.common import (
    Category,
    Dict,
    NotifyMode,
    Origin,
    TimeWindow,
    Transport,
    WhenSlot,
)


class SearchParams(CamelModel):
    duration_min: Literal[30, 60, 120, 180]
    when: WhenSlot
    from_: Origin = Field(alias="from")
    window: TimeWindow | None = Optional()
    company_id: str | None = Optional()

class Stats(CamelModel):
    hours_year: float
    hours_month: float
    deals: int
    streak_weeks: int
    bank_balance: float

class Roles(CamelModel):
    coordinator: bool
    mentor_eligible: bool

class Me(CamelModel):
    id: str
    first_name: str
    onboarded: bool
    consent_at: AwareDatetime | None
    university: Dict | None
    district: Dict | None
    interests: list[Category]
    transport: Transport
    notify: NotifyMode
    pause_until: AwareDatetime | None
    weekly_search: SearchParams | None
    stats: Stats
    roles: Roles

class ProfilePatch(CamelModel):
    interests: list[Category] | None = None
    transport: Transport | None = None
    notify: NotifyMode | None = None
    university_id: str | None = None
    district_id: str | None = None

    @field_validator("interests")
    @classmethod
    def _dedupe_interests(cls, v: list[Category] | None) -> list[Category] | None:
        return None if v is None else list(dict.fromkeys(v))

class OnboardingIn(CamelModel):
    university_id: str
    district_id: str

class WeeklySearchIn(CamelModel):
    """`PUT /me/weekly-search {params: SearchParams | null}` — null выключает подписку."""

    params: SearchParams | None
