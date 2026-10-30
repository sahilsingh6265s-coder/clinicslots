"""Unit tests for the pure slot-generation function (no database, no HTTP)."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.services.slot_service import generate_slots

TZ = ZoneInfo("Asia/Kolkata")
DAY = date(2030, 1, 7)  # a Monday, safely in the future
LONG_AGO = datetime(2000, 1, 1, tzinfo=timezone.utc)


def starts(slots):
    return [s.strftime("%H:%M") for s, _ in slots]


def test_window_split_into_slots():
    slots = generate_slots(DAY, [(time(10, 0), time(12, 0))], 30, set(), LONG_AGO, TZ)
    assert starts(slots) == ["10:00", "10:30", "11:00", "11:30"]


def test_slot_end_is_start_plus_length():
    (start, end), *_ = generate_slots(DAY, [(time(10, 0), time(11, 0))], 30, set(), LONG_AGO, TZ)
    assert (end - start).total_seconds() == 30 * 60


def test_two_windows_in_one_day():
    windows = [(time(16, 0), time(17, 0)), (time(10, 0), time(11, 0))]
    slots = generate_slots(DAY, windows, 30, set(), LONG_AGO, TZ)
    assert starts(slots) == ["10:00", "10:30", "16:00", "16:30"]  # sorted


def test_partial_slot_at_end_is_dropped():
    slots = generate_slots(DAY, [(time(10, 0), time(11, 15))], 30, set(), LONG_AGO, TZ)
    assert starts(slots) == ["10:00", "10:30"]


def test_booked_slot_is_removed():
    booked = {datetime(2030, 1, 7, 10, 30, tzinfo=TZ).astimezone(timezone.utc)}
    slots = generate_slots(DAY, [(time(10, 0), time(12, 0))], 30, booked, LONG_AGO, TZ)
    assert starts(slots) == ["10:00", "11:00", "11:30"]


def test_naive_booked_datetime_is_treated_as_utc():
    # SQLite returns naive datetimes; 05:00 UTC == 10:30 IST
    booked = {datetime(2030, 1, 7, 5, 0)}
    slots = generate_slots(DAY, [(time(10, 0), time(11, 0))], 30, booked, LONG_AGO, TZ)
    assert starts(slots) == ["10:00"]


def test_past_slots_are_removed():
    now = datetime(2030, 1, 7, 10, 40, tzinfo=TZ)  # 10:40 IST
    slots = generate_slots(DAY, [(time(10, 0), time(12, 0))], 30, set(), now, TZ)
    assert starts(slots) == ["11:00", "11:30"]


def test_whole_day_in_the_past_is_empty():
    now = datetime(2030, 1, 8, tzinfo=TZ)
    assert generate_slots(DAY, [(time(10, 0), time(12, 0))], 30, set(), now, TZ) == []


def test_no_windows_means_no_slots():
    assert generate_slots(DAY, [], 30, set(), LONG_AGO, TZ) == []
