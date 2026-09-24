from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.db.enums import Category, CertPeriod, Transport
from app.domain import checkin_code
from app.domain.certificate import CODE_ALPHABET, new_code, normalize_code, period_label
from app.domain.ics import BusyEvent, build_event, parse_busy
from app.domain.search import Candidate, Origin, best_route, counts, search
from app.domain.travel import HaversineEstimator, Point, haversine_km
from app.domain.windows import (
    Window,
    ceil_minutes,
    fallback_window,
    free_slots,
    intersect,
    window_from_slots,
)

MSK = ZoneInfo("Europe/Moscow")

def msk(*args: int) -> datetime:
    return datetime(*args, tzinfo=MSK)  # type: ignore[misc]

def test_totp_rfc6238_vector() -> None:
    secret = b"12345678901234567890"
    assert checkin_code._hotp(secret, 1) == "287082"

def test_checkin_code_steps() -> None:
    secret = checkin_code.new_secret()
    now = datetime(2026, 9, 29, 9, 0, 30, tzinfo=UTC)
    code = checkin_code.current_code(secret, now)
    assert code.qr_payload == f"vremya:checkin:{code.code}"
    assert code.expires_at == datetime(2026, 9, 29, 9, 1, tzinfo=UTC)
    assert checkin_code.check(secret, code.code, now) == "ok"
    assert checkin_code.check(secret, code.qr_payload, now) == "ok"
    assert checkin_code.verify(secret, code.code, now + timedelta(seconds=60))
    assert checkin_code.check(secret, code.code, now + timedelta(seconds=120)) == "expired"
    assert checkin_code.check(secret, "12ab", now) == "wrong_code"
    other = "000000" if code.code != "000000" else "111111"
    assert checkin_code.check(secret, other, now) in ("wrong_code", "expired", "ok")

def test_travel_estimate() -> None:
    a, b = Point(55.7904, 49.1208), Point(55.7899, 49.1150)
    km = haversine_km(a, b)
    assert 0.3 < km < 0.45
    est = HaversineEstimator()
    assert est.minutes(a, b, Transport.WALK) == 10
    assert est.minutes(a, a, Transport.TRANSIT) == 3

ICS = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VTIMEZONE\r
TZID:Europe/Moscow\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
UID:hist\r
DTSTART;TZID=Europe/Moscow:20260901T093000\r
DTEND;TZID=Europe/Moscow:20260901T110000\r
RRULE:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261231T000000Z\r
EXDATE;TZID=Europe/Moscow:20261001T093000\r
SUMMARY:История\r
BEGIN:VALARM\r
TRIGGER:-PT15M\r
END:VALARM\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:math\r
DTSTART:20260929T100000Z\r
DURATION:PT1H30M\r
SUMMARY:Матан\\, лекция\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:hist\r
RECURRENCE-ID;TZID=Europe/Moscow:20261006T093000\r
DTSTART;TZID=Europe/Moscow:20261006T150000\r
DTEND;TZID=Europe/Moscow:20261006T163000\r
SUMMARY:История (перенос)\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:holiday\r
DTSTART;VALUE=DATE:20261104\r
SUMMARY:Праздник\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:gone\r
DTSTART:20260930T100000Z\r
DTEND:20260930T110000Z\r
STATUS:CANCELLED\r
SUMMARY:Отменено\r
END:VEVENT\r
END:VCALENDAR\r
"""

def test_parse_busy_expands_rules() -> None:
    events = parse_busy(ICS, MSK, msk(2026, 9, 29), msk(2026, 10, 9))
    got = [(e.starts_at.astimezone(MSK).strftime("%d %H:%M"), e.title) for e in events]
    assert got == [
        ("29 09:30", "История"),
        ("29 13:00", "Матан, лекция"),
        ("06 15:00", "История (перенос)"),
        ("08 09:30", "История"),
    ]

def test_parse_busy_rejects_garbage() -> None:
    from app.domain.ics import IcsError

    with pytest.raises(IcsError):
        parse_busy("hello", MSK, msk(2026, 9, 29), msk(2026, 10, 9))

def test_build_event_escapes() -> None:
    body = build_event(
        uid="x@v",
        starts_at=msk(2026, 9, 30, 18, 0),
        ends_at=msk(2026, 9, 30, 19, 30),
        summary="Разбор книг; и, всё",
        location="ул. Баумана, 19",
        description="Строка 1\nСтрока 2 " + "длинно " * 20,
        stamp=msk(2026, 9, 29, 12, 0),
    )
    assert "DTSTART:20260930T150000Z" in body
    assert r"SUMMARY:Разбор книг\; и\, всё" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    back = parse_busy(body, MSK, msk(2026, 9, 1), msk(2026, 11, 1))
    assert back[0].title == "Разбор книг; и, всё"

def test_free_slots_between_events() -> None:
    events = [
        BusyEvent(msk(2026, 9, 29, 9, 30), msk(2026, 9, 29, 11, 0), "История"),
        BusyEvent(msk(2026, 9, 29, 11, 30), msk(2026, 9, 29, 13, 0), "Матан"),
        BusyEvent(msk(2026, 9, 29, 14, 0), msk(2026, 9, 29, 21, 30), "Лаба"),
    ]
    slots = free_slots(events, MSK)
    assert [
        (s.starts_at.hour, s.starts_at.minute, s.ends_at.hour, s.after_label) for s in slots
    ] == [
        (8, 0, 9, "до «История»"),
        (13, 0, 14, "после «Матан»"),
    ]

def test_window_from_slots_and_fallback() -> None:
    now = msk(2026, 9, 29, 12, 2)
    slots = [
        Window(msk(2026, 9, 29, 11, 10), msk(2026, 9, 29, 13, 10)),
        Window(msk(2026, 9, 29, 14, 40), msk(2026, 9, 29, 17, 0)),
        Window(msk(2026, 9, 30, 15, 0), msk(2026, 9, 30, 22, 0)),
    ]
    assert window_from_slots(slots, "now", 60, now, MSK) == Window(
        msk(2026, 9, 29, 12, 5), msk(2026, 9, 29, 13, 5)
    )
    assert window_from_slots(slots, "tonight", 60, now, MSK) is None
    assert window_from_slots(slots, "tomorrow", 180, now, MSK) == Window(
        msk(2026, 9, 30, 17, 30), msk(2026, 9, 30, 22, 0)
    )
    assert window_from_slots(slots, "weekend", 60, now, MSK) is None

    ev, we = time(17, 30), time(11, 0)
    assert fallback_window("tonight", 60, now, MSK, ev, we) == Window(
        msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 18, 30)
    )
    assert fallback_window("tomorrow", 30, now, MSK, ev, we).starts_at == msk(2026, 9, 30, 17, 30)
    assert fallback_window("weekend", 120, now, MSK, ev, we).starts_at == msk(2026, 10, 3, 11, 0)
    assert fallback_window("now", 30, now, MSK, ev, we).starts_at == msk(2026, 9, 29, 12, 5)
    assert fallback_window("tonight", 60, msk(2026, 9, 29, 18, 1), MSK, ev, we).starts_at == msk(
        2026, 9, 29, 18, 5
    )

def test_ceil_and_intersect() -> None:
    assert ceil_minutes(msk(2026, 9, 29, 12, 0)) == msk(2026, 9, 29, 12, 0)
    assert ceil_minutes(msk(2026, 9, 29, 12, 0, 1)) == msk(2026, 9, 29, 12, 5)
    a = Window(msk(2026, 9, 29, 17, 0), msk(2026, 9, 29, 19, 40))
    b = Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 21, 0))
    assert intersect([a, b]) == Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 19, 40))
    assert intersect([]) is None
    assert intersect([a, Window(msk(2026, 9, 29, 20, 0), msk(2026, 9, 29, 21, 0))]) is None

CAMPUS = Point(55.7904, 49.1208)

class FixedEstimator:
    def __init__(self, minutes: int) -> None:
        self.value = minutes

    def minutes(self, a: Point, b: Point, transport: Transport) -> int:
        return self.value

def cand(key: int, start: datetime, minutes: int, **kw: object) -> Candidate:
    import uuid

    defaults: dict[str, object] = {
        "category": Category.BOOKS,
        "point": CAMPUS,
        "district_id": "vakh",
        "online": False,
        "seats_left": 3,
    }
    defaults.update(kw)
    return Candidate(
        id=uuid.UUID(int=key),
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        **defaults,  # type: ignore[arg-type]
    )

def test_search_campus_slack_and_fit() -> None:
    window = Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 19, 30))
    est = FixedEstimator(10)
    origin = Origin(kind="campus", point=CAMPUS)
    items = [
        cand(1, msk(2026, 9, 29, 17, 45), 60),
        cand(2, msk(2026, 9, 29, 17, 35), 30),
        cand(3, msk(2026, 9, 29, 18, 0), 60, category=Category.PEOPLE),
        cand(4, msk(2026, 9, 29, 18, 0), 60, seats_left=0),
        cand(5, msk(2026, 9, 29, 18, 0), 60, seats_left=0, booked_by_me=True),
        cand(6, msk(2026, 9, 29, 18, 30), 30, online=True, category=Category.ONLINE),
    ]
    busy = [Window(msk(2026, 9, 29, 18, 50), msk(2026, 9, 29, 19, 10))]
    found = search(items, window, origin, Transport.WALK, est, busy)
    assert [m.candidate.id.int for m in found] == [1, 5]
    found = search(items, window, origin, Transport.WALK, est)
    assert [m.candidate.id.int for m in found] == [1, 3, 5, 6]
    first = found[0]
    assert first.travel_min == 10 and first.slack_min == 5 and first.fit == "tight"
    online = found[-1]
    assert online.travel_min == 0 and online.slack_min == 30 and online.near
    c = counts(found)
    assert c["all"] == 4 and c["books"] == 2 and c["people"] == 1 and c["online"] == 1
    assert c["near"] == 4 and c["animals"] == 0

def test_search_home_by_district() -> None:
    window = Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 19, 30))
    origin = Origin(kind="home", home_district="vakh", districts=frozenset({"vakh", "d1"}))
    items = [
        cand(1, msk(2026, 9, 29, 17, 30), 60),
        cand(2, msk(2026, 9, 29, 18, 0), 60, district_id="d1"),
        cand(3, msk(2026, 9, 29, 18, 0), 60, district_id="d5"),
    ]
    found = search(items, window, origin, Transport.WALK, FixedEstimator(99))
    assert [(m.candidate.id.int, m.travel_min, m.slack_min, m.near) for m in found] == [
        (1, None, 0, True),
        (2, None, 30, False),
    ]

def test_best_route_prefers_more_hours() -> None:
    window = Window(msk(2026, 9, 29, 17, 30), msk(2026, 9, 29, 21, 0))
    origin = Origin(kind="campus", point=CAMPUS)
    items = [
        cand(1, msk(2026, 9, 29, 18, 0), 40),
        cand(2, msk(2026, 9, 29, 19, 0), 60),
        cand(3, msk(2026, 9, 29, 18, 45), 90),
        cand(4, msk(2026, 9, 29, 18, 0), 30),
    ]
    plan = best_route(items, window, origin, Transport.WALK, FixedEstimator(5))
    assert plan is not None
    assert (plan.first.id.int, plan.second.id.int, plan.walk_min) == (4, 3, 5)
    assert best_route(items, window, origin, Transport.WALK, FixedEstimator(16)) is None

def test_certificate_codes_and_labels() -> None:
    code = new_code()
    assert len(code) == 7 and code[3] == "-"
    assert all(ch in CODE_ALPHABET for ch in code.replace("-", ""))
    assert not set("01OI") & set(CODE_ALPHABET)
    assert len(CODE_ALPHABET) == 32
    assert normalize_code("k7q42m") == "K7Q-42M"
    assert normalize_code("K7Q-42O") is None
    assert period_label(CertPeriod.SEMESTER, date(2026, 9, 29)) == "с 1 сентября"
    assert period_label(CertPeriod.SEMESTER, date(2027, 3, 1)) == "с 1 февраля"
    assert period_label(CertPeriod.ALL, date(2027, 3, 1)) == "всё время"
