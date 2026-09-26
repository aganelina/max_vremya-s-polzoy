import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.db.enums import BookingStatus
from app.domain.coord import (
    CoordError,
    CsvRow,
    UrgentCandidate,
    attendance_csv,
    can_undo_review,
    micro_hours,
    participant_status,
    pick_recipients,
    recipient_limit,
    validate_new_shift,
)
from app.domain.hours import shift_hours
from app.domain.metrics import OrgRow, funnel, org_lines, pilot_average
from app.domain.orgs import PNG_MAGIC, check_png, clean_inn

NOW = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
MSK = ZoneInfo("Europe/Moscow")

def test_shift_hours_rounds_to_tenth() -> None:
    assert shift_hours(NOW, NOW + timedelta(minutes=90)) == Decimal("1.5")
    assert shift_hours(NOW, NOW + timedelta(minutes=40)) == Decimal("0.7")
    assert micro_hours(15) == Decimal("0.3")
    assert micro_hours(5) == Decimal("0.1")

@pytest.mark.parametrize(
    ("title", "minutes", "capacity", "delta", "code"),
    [
        ("", 60, 5, 60, "invalid_title"),
        ("x" * 81, 60, 5, 60, "invalid_title"),
        ("ok", 14, 5, 60, "invalid_duration"),
        ("ok", 481, 5, 60, "invalid_duration"),
        ("ok", 60, 0, 60, "invalid_capacity"),
        ("ok", 60, 201, 60, "invalid_capacity"),
        ("ok", 60, 5, 0, "starts_in_past"),
    ],
)
def test_validate_new_shift_errors(
    title: str, minutes: int, capacity: int, delta: int, code: str
) -> None:
    with pytest.raises(CoordError) as exc:
        validate_new_shift(title, NOW + timedelta(minutes=delta), minutes, capacity, NOW)
    assert exc.value.code == code and exc.value.status == 422

def test_validate_new_shift_ok() -> None:
    assert validate_new_shift("  Смена  ", NOW + timedelta(hours=1), 480, 200, NOW) == "Смена"

def test_participant_status() -> None:
    start = NOW
    assert participant_status(BookingStatus.GOING, None, start) == "booked"
    assert participant_status(BookingStatus.MANUAL, NOW, start) == "manual"
    assert participant_status(BookingStatus.NO_SHOW, None, start) == "no_show"
    on_time = start + timedelta(minutes=10)
    assert participant_status(BookingStatus.CHECKED_IN, on_time, start) == "came"
    late = start + timedelta(minutes=11)
    assert participant_status(BookingStatus.DONE, late, start) == "late"

def test_recipient_limit() -> None:
    assert recipient_limit(1) == 15
    assert recipient_limit(7) == 21
    assert recipient_limit(20) == 40

def test_pick_recipients_prefers_open_windows() -> None:
    def cand(window: bool, district: bool, campus: bool = False) -> UrgentCandidate:
        return UrgentCandidate(uuid.uuid4(), window, district, campus)

    far = cand(False, False)
    near = cand(False, True)
    campus = cand(False, False, True)
    windowed = cand(True, False)
    picked = pick_recipients([far, near, campus, windowed], limit=2)
    assert picked == [windowed, near]
    assert far not in pick_recipients([far, near, campus, windowed], limit=10)

def test_can_undo_review_within_ten_minutes() -> None:
    assert can_undo_review(NOW, NOW + timedelta(minutes=10))
    assert not can_undo_review(NOW, NOW + timedelta(minutes=11))
    assert not can_undo_review(None, NOW)

def test_attendance_csv_has_bom_and_header() -> None:
    body = attendance_csv(
        [
            CsvRow(NOW, "Смена, книги", "Алина", "came", NOW, Decimal("1.5")),
            CsvRow(NOW, "Смена", "Тимур", "no_show", None, None),
        ],
        MSK,
    )
    lines = body.split("\r\n")
    assert body.startswith("﻿")
    assert lines[0] == "﻿date,shift,name,status,checked_in_at,hours"
    assert lines[1] == '2026-09-29,"Смена, книги",Алина,came,2026-09-29T12:00+03:00,1.5'
    assert lines[2] == "2026-09-29,Смена,Тимур,no_show,,"

def test_funnel_hides_small_groups() -> None:
    steps = funnel(10, 4, 2)
    assert [s.value for s in steps] == [10, 4, 0]
    assert steps[1].note == "40% от окон"

def test_org_lines_own_org_and_pilot_average() -> None:
    own, other, tiny = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        OrgRow(own, "Своя", 4, 3, 4, Decimal(6)),
        OrgRow(other, "Чужая", 5, 4, 5, Decimal(4)),
        OrgRow(tiny, "Маленькая", 2, 2, 2, Decimal(2)),
    ]
    lines = org_lines(rows, own)
    assert [line.name for line in lines] == ["Своя", "В среднем по пилоту"]
    assert lines[0].attendance == 0.75
    avg = pilot_average(rows)
    assert avg is not None and avg.hours == 5.0 and avg.attendance == 0.78
    assert [line.name for line in org_lines(rows, None)][:2] == ["Своя", "Чужая"]

def test_clean_inn_and_png() -> None:
    assert clean_inn(" 1655000000 ") == "1655000000"
    assert clean_inn("") is None
    with pytest.raises(CoordError):
        clean_inn("123")
    assert check_png(PNG_MAGIC + b"x", "seal")
    with pytest.raises(CoordError) as exc:
        check_png(b"GIF89a", "seal")
    assert exc.value.code == "seal_not_png"
    with pytest.raises(CoordError) as exc:
        check_png(PNG_MAGIC + b"x" * (1024 * 1024), "seal")
    assert exc.value.code == "seal_too_large"
