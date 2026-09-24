import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.ics import IcsError, parse_busy

TZ = ZoneInfo("Europe/Moscow")
START = datetime(2026, 9, 28, tzinfo=TZ)
END = START + timedelta(days=28)

def _cal(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\n" + "".join(events) + "END:VCALENDAR\r\n"

def _event(uid: str, dtstart: str, rrule: str, dtend: str | None = None) -> str:
    end = dtend or dtstart[:9] + "103000"
    return (
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:Пара\r\n"
        f"DTSTART;TZID=Europe/Moscow:{dtstart}\r\nDTEND;TZID=Europe/Moscow:{end}\r\n"
        f"RRULE:{rrule}\r\nEND:VEVENT\r\n"
    )

def test_old_biweekly_rule_keeps_all_occurrences_in_range() -> None:
    text = _cal(_event("a", "20250901T090000", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"))
    busy = parse_busy(text, TZ, START, END)
    got = [e.starts_at.date().isoformat() for e in busy]
    assert got == ["2026-09-28", "2026-10-12"]

def test_old_daily_rule_starts_at_range() -> None:
    text = _cal(_event("d", "19000101T090000", "FREQ=DAILY;INTERVAL=3"))
    busy = parse_busy(text, TZ, START, START + timedelta(days=9))
    assert len(busy) == 3 and all(e.starts_at >= START for e in busy)

def test_many_events_rejected_fast() -> None:
    text = _cal(*(_event(str(i), "19000101T090000", "FREQ=DAILY") for i in range(10_000)))
    t = time.perf_counter()
    with pytest.raises(IcsError):
        parse_busy(text, TZ, START, END)
    assert time.perf_counter() - t < 2

def test_huge_count_hits_step_budget() -> None:
    text = _cal(*(_event(str(i), "19000101T090000", "FREQ=DAILY;COUNT=99999") for i in range(50)))
    with pytest.raises(IcsError, match="too_complex"):
        parse_busy(text, TZ, START, END)

@pytest.mark.parametrize("rule", ["FREQ=DAILY;INTERVAL=999999999999", "FREQ=DAILY;INTERVAL=x"])
def test_bad_numbers_are_ics_errors(rule: str) -> None:
    with pytest.raises(IcsError):
        parse_busy(_cal(_event("x", "20260901T090000", rule)), TZ, START, END)
