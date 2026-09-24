from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas.base import CamelModel, Optional
from app.api.schemas.common import Category, TimeWindow

BookingStatus = Literal["going", "checked_in", "manual", "done", "cancelled", "no_show"]

class Org(CamelModel):
    id: str
    name: str
    verified: bool

class Booking(CamelModel):
    id: str
    deal_id: str
    status: BookingStatus
    checked_in_at: AwareDatetime | None

class Deal(CamelModel):
    id: str
    title: str
    org: Org
    category: Category
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    hours: float
    address: str
    address_note: str | None = Optional()
    description: str
    travel_min: int | None
    capacity: int
    quorum: bool = False
    taken: int
    going_initials: list[str]
    check_in_from: AwareDatetime
    check_in_to: AwareDatetime
    cancel_until: AwareDatetime
    instructions_at: AwareDatetime
    my_booking: Booking | None
    impact: str | None = Optional()

class SearchResultItem(CamelModel):
    deal: Deal
    slack_min: int
    fit: Literal["ok", "tight"]

class SearchResult(CamelModel):
    """`window` — окно подбора; null только при `windowSource = none` (в расписании нет окна
    нужной длины в выбранный день). Тогда `items` пусты, а `nextWindow` — ближайшее свободное
    окно расписания нужной длины в любой день (или null)."""

    window: TimeWindow | None
    window_source: Literal["explicit", "company", "schedule", "fallback", "none"]
    next_window: TimeWindow | None
    items: list[SearchResultItem]
    counts: dict[str, int]

class SearchPreview(CamelModel):
    count: int

class BookIn(CamelModel):
    company_id: str | None = None
    invite_token: str | None = None

class Link(CamelModel):
    link: str

class HistoryItem(CamelModel):
    id: str
    title: str
    date: AwareDatetime
    place: str
    hours: float

class PastBooking(CamelModel):
    id: str
    deal_id: str
    title: str
    starts_at: AwareDatetime
    status: str
    can_contact: bool

class MyDeals(CamelModel):
    upcoming: list[Deal]
    history: list[HistoryItem]
    past: list[PastBooking]

class FriendInvite(CamelModel):
    status: Literal["ok", "full", "expired"]
    inviter_name: str | None
    deal: Deal | None

class SeatTransfer(CamelModel):
    status: Literal["ok", "taken", "expired"]
    from_name: str | None
    deal: Deal | None

class CheckInIn(CamelModel):
    code: str = Field(max_length=64)

class CheckInResult(CamelModel):
    ok: bool
    checked_in_at: AwareDatetime | None = Optional()
    error: Literal["expired", "wrong_code", "too_early", "too_late"] | None = Optional()
    late: bool | None = Optional()

class FreeWindow(CamelModel):
    id: str
    day: str
    from_: str = Field(alias="from")
    to: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    after: str
    place: str

class Schedule(CamelModel):
    file_name: str | None
    windows: list[FreeWindow]

class CompanyMember(CamelModel):
    id: str
    first_name: str
    initial: str
    is_me: bool
    window: TimeWindow | None
    reminded_at: AwareDatetime | None

class CompanyDeal(CamelModel):
    deal: Deal
    votes: list[str]

class Company(CamelModel):
    id: str
    date: AwareDatetime
    common_window: TimeWindow | None
    members: list[CompanyMember]
    invite_link: str
    deals: list[CompanyDeal]
    picked_deal_id: str | None

class CompanyIn(CamelModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

class CompanyWindowIn(CamelModel):
    window: TimeWindow | None

class PickIn(CamelModel):
    deal_id: str | None

class RouteLeg(CamelModel):
    deal: Deal
    walk_to_next_min: int | None

class Route(CamelModel):
    window: TimeWindow
    legs: list[RouteLeg]

class RouteBookIn(CamelModel):
    deal_ids: list[str] = Field(min_length=1, max_length=5)

class CertificateRow(CamelModel):
    date: AwareDatetime
    title: str
    org: str
    hours: float

class Participant(CamelModel):
    first_name: str
    university: str

class Certificate(CamelModel):
    period: Literal["semester", "all"]
    period_label: str
    generated_at: AwareDatetime
    participant: Participant
    rows: list[CertificateRow]
    total: float
    verify_code: str
    verify_url: str

class ShareIn(CamelModel):
    period: Literal["semester", "all"] = "semester"
