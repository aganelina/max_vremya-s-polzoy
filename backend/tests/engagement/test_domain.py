from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.api.errors import Conflict, Unprocessable
from app.domain.bank import check_can_ask, district_label
from app.domain.deal_times import cancel_until, check_in_window, instructions_at
from app.domain.hours import shift_hours
from app.domain.mentorship import interests_overlap, is_eligible
from app.domain.micro import normalize_answer, pick_next

MSK = ZoneInfo("Europe/Moscow")

def test_pick_next_rotates_after_skipped() -> None:
    assert pick_next(["a", "b", "c"], None) == "a"
    assert pick_next(["a", "b", "c"], "a") == "b"
    assert pick_next(["a", "b", "c"], "c") == "a"
    assert pick_next(["a", "b"], "x") == "a"
    assert pick_next(["a"], "a") == "a"
    assert pick_next([], "a") is None

def test_answer_needs_ten_chars() -> None:
    assert normalize_answer("  Десять букв  ") == "Десять букв"
    with pytest.raises(Unprocessable) as exc:
        normalize_answer("  коротко  ")
    assert exc.value.code == "answer_too_short"

def test_can_ask_limits() -> None:
    check_can_ask(2, Decimal("1"), Decimal("1"))
    with pytest.raises(Conflict) as exc:
        check_can_ask(3, Decimal("1"), Decimal("5"))
    assert exc.value.code == "too_many_requests"
    with pytest.raises(Conflict) as exc:
        check_can_ask(0, Decimal("2"), Decimal("1.5"))
    assert exc.value.code == "insufficient_balance"

def test_district_label() -> None:
    assert district_label("Вахитовский") == "Вахитовский район"
    assert district_label(None) == ""

def test_mentor_rules() -> None:
    assert is_eligible(3, 3) and not is_eligible(2, 3)
    assert interests_overlap(["books", "people"], ["people"])
    assert not interests_overlap([], ["people"])

def test_deal_times() -> None:
    starts = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    early = instructions_at(starts, datetime(2026, 9, 29, 9, 0, tzinfo=UTC))
    assert early == datetime(2026, 9, 30, 19, 0, tzinfo=MSK)
    assert cancel_until(starts) == datetime(2026, 10, 1, 11, 0, tzinfo=UTC)
    assert check_in_window(starts) == (
        datetime(2026, 10, 1, 13, 45, tzinfo=UTC),
        datetime(2026, 10, 1, 14, 30, tzinfo=UTC),
    )
    late_booking = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    assert instructions_at(starts, late_booking) == late_booking

def test_shift_hours() -> None:
    a = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    assert shift_hours(a, a.replace(hour=15, minute=30)) == Decimal("1.5")
    assert shift_hours(a, a.replace(minute=40)) == Decimal("0.7")
    assert shift_hours(a, a.replace(minute=15)) == Decimal("0.3")
