import datetime as dt
from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas.base import CamelModel
from app.api.schemas.common import Category

ShiftPlace = Literal["org", "district", "online"]
ShiftStatus = Literal["open", "cancelled", "finished"]
MessageAudience = Literal["all", "waiting", "came"]

class Org(CamelModel):
    id: str
    name: str
    verified: bool

class Shift(CamelModel):
    id: str
    title: str
    org: Org
    category: Category
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    address: str
    capacity: int
    booked: int
    quorum: bool
    instructions: str
    place: ShiftPlace
    status: ShiftStatus

class NextShift(CamelModel):
    shift: Shift
    going: int

class CoordinatorHome(CamelModel):
    next: NextShift | None
    shifts: list[Shift]

class Participant(CamelModel):
    id: str
    first_name: str
    status: Literal["booked", "came", "late", "no_show", "manual"]
    checked_in_at: AwareDatetime | None

class ShiftAttendance(CamelModel):
    shift: Shift
    participants: list[Participant]

class CheckInCode(CamelModel):
    code: str
    qr_payload: str
    expires_at: AwareDatetime

class NewShift(CamelModel):
    title: str
    date: dt.date
    time: dt.time
    duration_min: int
    capacity: int
    category: Category
    place: ShiftPlace
    instructions: str = Field(default="", max_length=2000)
    quorum: bool = False

class UrgentCallIn(CamelModel):
    what: str = Field(min_length=1, max_length=200)
    where: str = Field(min_length=1, max_length=200)
    start_in_min: Literal[15, 30, 45, 60]
    people: int

class UrgentResponse(CamelModel):
    name: str
    at: AwareDatetime

class UrgentCallStatus(CamelModel):
    id: str
    shift_id: str
    what: str
    people: int
    reached: int
    responses: list[UrgentResponse]

class ReviewItem(CamelModel):
    id: str
    author_name: str
    minutes: int
    task: str
    answer: str

class ReviewQueue(CamelModel):
    items: list[ReviewItem]
    accepted_today: int
    returned_today: int

class ReviewIn(CamelModel):
    verdict: Literal["accept", "return"]
    note: str | None = None

class FunnelStep(CamelModel):
    label: str
    value: int
    note: str

class OrgMetrics(CamelModel):
    name: str
    attendance: float
    hours: float

class Metrics(CamelModel):
    period_label: str
    hours: float
    participants: int
    returned_share: float
    funnel: list[FunnelStep]
    orgs: list[OrgMetrics]

class Coordinator(CamelModel):
    id: str
    name: str
    owner: bool
    me: bool
    revoked: bool

class Invite(CamelModel):
    link: str
    expires_at: AwareDatetime

class OrgAccess(CamelModel):
    org_name: str
    shifts_this_month: int
    coordinators: list[Coordinator]
    invite: Invite | None

class RevokeIn(CamelModel):
    revoked: bool

class Audience(CamelModel):
    key: MessageAudience
    names: list[str]

class MessageIn(CamelModel):
    audience: MessageAudience
    text: str

class MessageSent(CamelModel):
    sent: int

class NewMicroTask(CamelModel):
    title: str
    text: str
    minutes: int
    answers_needed: int = Field(ge=1, le=500)
    deadline: AwareDatetime | None = None

class MicroTaskPatch(CamelModel):
    active: bool

class CoordMicroTask(CamelModel):
    id: str
    title: str
    text: str
    minutes: int
    answers_needed: int
    deadline: AwareDatetime | None
    active: bool
    pending: int
    accepted: int
    created_at: AwareDatetime
