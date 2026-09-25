from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from app.api.schemas.base import CamelModel, Optional


class Org(CamelModel):
    id: str
    name: str
    verified: bool

class MicroTask(CamelModel):
    id: str
    title: str
    org: Org
    minutes: int
    text: str
    status: Literal["free", "taken", "sent", "accepted", "returned"]
    deadline: AwareDatetime | None
    answer: str
    review_note: str | None = Optional()

class MicroAnswerIn(CamelModel):
    answer: str = Field(max_length=4000)

class HelpRequest(CamelModel):
    id: str
    text: str
    hours: float
    when: str
    district: str
    mine: bool
    responded: bool
    helper_name: str | None
    status: Literal["open", "matched", "closed"]

class HourBank(CamelModel):
    balance: float
    reserved: float
    max_open_requests: int
    others: list[HelpRequest]
    mine: list[HelpRequest]

class AskHelpIn(CamelModel):
    text: str = Field(min_length=1, max_length=200)
    hours: Decimal = Field(gt=0, le=Decimal("10"))
    when: str | None = Field(default=None, max_length=60)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v

    @field_validator("hours")
    @classmethod
    def _one_digit(cls, v: Decimal) -> Decimal:
        q = v.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if q <= 0:
            raise ValueError("too_small")
        return q

from app.api.schemas.deals import Deal  # noqa: E402 — общая схема карточки дела


class MentorRequest(CamelModel):
    id: str
    newbie_name: str
    deal: Deal

class MentorPair(CamelModel):
    id: str
    newbie_name: str
    deal_title: str
    starts_at: AwareDatetime

class Mentorship(CamelModel):
    eligible: bool
    deals_done: int
    deals_required: int
    accepting: bool
    requests: list[MentorRequest]
    pairs: list[MentorPair]

class MentorshipPatch(CamelModel):
    accepting: bool
