from enum import StrEnum

from sqlalchemy import Enum


class Category(StrEnum):
    PEOPLE = "people"
    ANIMALS = "animals"
    ECOLOGY = "ecology"
    BOOKS = "books"
    THINGS = "things"
    ONLINE = "online"

class Transport(StrEnum):
    WALK = "walk"
    TRANSIT = "transit"
    SCOOTER = "scooter"

class NotifyMode(StrEnum):
    ALL = "all"
    MINE = "mine"
    PAUSE = "pause"

class OrgStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class OrgRole(StrEnum):
    OWNER = "owner"
    COORDINATOR = "coordinator"

class ShiftPlace(StrEnum):
    ORG = "org"
    DISTRICT = "district"
    ONLINE = "online"

class ShiftStatus(StrEnum):
    OPEN = "open"
    CANCELLED = "cancelled"
    FINISHED = "finished"

class BookingStatus(StrEnum):
    GOING = "going"
    CHECKED_IN = "checked_in"
    DONE = "done"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    MANUAL = "manual"

class LedgerSource(StrEnum):
    SHIFT = "shift"
    MICRO = "micro"
    BANK_HELP = "bank_help"
    BANK_SPEND = "bank_spend"

class TransferStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    EXPIRED = "expired"

class MicroAnswerStatus(StrEnum):
    TAKEN = "taken"
    SENT = "sent"
    ACCEPTED = "accepted"
    RETURNED = "returned"
    RELEASED = "released"

class HelpStatus(StrEnum):
    OPEN = "open"
    MATCHED = "matched"
    CLOSED = "closed"
    CANCELLED = "cancelled"

class MentorRequestStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"

class MessageAudience(StrEnum):
    ALL = "all"
    WAITING = "waiting"
    CAME = "came"

class RelayDirection(StrEnum):
    TO_PARTICIPANT = "to_participant"
    TO_COORDINATOR = "to_coordinator"

class CertPeriod(StrEnum):
    SEMESTER = "semester"
    ALL = "all"

def pg_enum[E: StrEnum](enum_cls: type[E], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )

CATEGORY = pg_enum(Category, "category")
TRANSPORT = pg_enum(Transport, "transport")
NOTIFY_MODE = pg_enum(NotifyMode, "notify_mode")
ORG_STATUS = pg_enum(OrgStatus, "org_status")
ORG_ROLE = pg_enum(OrgRole, "org_role")
SHIFT_PLACE = pg_enum(ShiftPlace, "shift_place")
SHIFT_STATUS = pg_enum(ShiftStatus, "shift_status")
BOOKING_STATUS = pg_enum(BookingStatus, "booking_status")
LEDGER_SOURCE = pg_enum(LedgerSource, "ledger_source")
TRANSFER_STATUS = pg_enum(TransferStatus, "transfer_status")
MICRO_ANSWER_STATUS = pg_enum(MicroAnswerStatus, "micro_answer_status")
HELP_STATUS = pg_enum(HelpStatus, "help_status")
MENTOR_REQUEST_STATUS = pg_enum(MentorRequestStatus, "mentor_request_status")
MESSAGE_AUDIENCE = pg_enum(MessageAudience, "message_audience")
RELAY_DIRECTION = pg_enum(RelayDirection, "relay_direction")
CERT_PERIOD = pg_enum(CertPeriod, "cert_period")
