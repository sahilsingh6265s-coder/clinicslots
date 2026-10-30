"""Slot generation: turn a doctor's weekly working windows into bookable slots.

Slots are NOT stored. They are calculated on request from the availability
rules, minus appointments that already exist. This keeps the data small and a
change in availability applies immediately.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import Availability


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC (SQLite drops tzinfo; PostgreSQL keeps it)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def generate_slots(
    day: date,
    windows: list[tuple[time, time]],
    slot_minutes: int,
    booked: set[datetime],
    now: datetime,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """Pure function (no database), so it is easy to test.

    Returns (start, end) pairs in the clinic timezone.
    A slot is kept only if it fits fully inside a window, is in the future,
    and is not already booked.
    """
    step = timedelta(minutes=slot_minutes)
    now_utc = as_utc(now)
    booked_utc = {as_utc(b) for b in booked}
    slots: list[tuple[datetime, datetime]] = []

    for start_t, end_t in sorted(windows):
        cursor = datetime.combine(day, start_t, tzinfo=tz)
        window_end = datetime.combine(day, end_t, tzinfo=tz)
        while cursor + step <= window_end:
            start_utc = cursor.astimezone(timezone.utc)
            if start_utc > now_utc and start_utc not in booked_utc:
                slots.append((cursor, cursor + step))
            cursor += step
    return slots


def get_free_slots(db: Session, doctor_id: int, slot_minutes: int, day: date, tz: ZoneInfo):
    """Load windows and booked appointments for the day, then generate slots."""
    rows = db.scalars(
        select(Availability).where(
            Availability.doctor_id == doctor_id, Availability.weekday == day.weekday()
        )
    ).all()
    windows = [(r.start_time, r.end_time) for r in rows]
    if not windows:
        return []

    day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    booked_rows = db.scalars(
        select(Appointment.slot_start).where(
            Appointment.doctor_id == doctor_id,
            Appointment.slot_start >= day_start,
            Appointment.slot_start < day_end,
            Appointment.status != AppointmentStatus.cancelled.value,
        )
    ).all()

    return generate_slots(
        day, windows, slot_minutes, set(booked_rows), datetime.now(timezone.utc), tz
    )
