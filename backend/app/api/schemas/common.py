from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas.base import CamelModel

Category = Literal["people", "animals", "ecology", "books", "things", "online"]
Transport = Literal["walk", "transit", "scooter"]
NotifyMode = Literal["all", "mine", "pause"]
Origin = Literal["campus", "home"]
WhenSlot = Literal["now", "tonight", "tomorrow", "weekend"]

class Dict(CamelModel):
    id: str
    name: str

class TimeWindow(CamelModel):
    """`{ from: string; to: string }` — ISO 8601 с зоной."""

    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
