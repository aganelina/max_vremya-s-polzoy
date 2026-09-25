from datetime import date
from decimal import Decimal

import pytest

from app.domain.hours import academic_year_start, semester_start, streak_weeks, to_hours


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2026, 8, 31), date(2025, 9, 1)),
        (date(2027, 1, 15), date(2026, 9, 1)),
        (date(2026, 12, 31), date(2026, 9, 1)),
    ],
)
def test_academic_year_start(day: date, expected: date) -> None:
    assert academic_year_start(day) == expected

@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2027, 1, 31), date(2026, 9, 1)),
        (date(2027, 2, 1), date(2027, 2, 1)),
        (date(2027, 8, 31), date(2027, 2, 1)),
    ],
)
def test_semester_start(day: date, expected: date) -> None:
    assert semester_start(day) == expected

TUESDAY = date(2026, 9, 29)

def test_streak_counts_consecutive_weeks() -> None:
    days = [date(2026, 9, 28), date(2026, 9, 23), date(2026, 9, 21), date(2026, 9, 14)]
    assert streak_weeks(days, TUESDAY) == 3

def test_streak_current_week_empty_does_not_break() -> None:
    assert streak_weeks([date(2026, 9, 27), date(2026, 9, 20)], TUESDAY) == 2

def test_streak_gap_breaks() -> None:
    assert streak_weeks([date(2026, 9, 29), date(2026, 9, 15)], TUESDAY) == 1
    assert streak_weeks([date(2026, 9, 14)], TUESDAY) == 0
    assert streak_weeks([], TUESDAY) == 0

def test_to_hours() -> None:
    assert to_hours(Decimal("1.50")) == 1.5
    assert to_hours(Decimal(0)) == 0.0
