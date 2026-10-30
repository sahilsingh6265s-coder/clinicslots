"""Admin dashboard numbers.

The rows for the date range are loaded once and counted in Python. That keeps
the timezone logic (which LOCAL day / time-of-day does a UTC timestamp belong
to?) in one portable place. At a much larger scale you would push this into
SQL (GROUP BY on a time-zone-converted date) and rely on an index.
"""
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.stats import DayCount, DoctorStats, SlotCount, StatsOut
from app.services.slot_service import as_utc

MAX_RANGE_DAYS = 366
TOP_SLOTS = 5


class InvalidRange(ValueError):
    pass


def compute_stats(db: Session, from_date: date, to_date: date, tz: ZoneInfo, tz_name: str) -> StatsOut:
    if to_date < from_date:
        raise InvalidRange("from_date must not be after to_date")
    if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
        raise InvalidRange(f"Date range cannot be longer than {MAX_RANGE_DAYS} days")

    start_utc = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)

    rows = db.execute(
        select(Appointment.doctor_id, Appointment.slot_start, Appointment.status).where(
            Appointment.slot_start >= start_utc, Appointment.slot_start < end_utc
        )
    ).all()

    cancelled_value = AppointmentStatus.cancelled.value
    by_status = {s.value: 0 for s in AppointmentStatus}
    per_day: Counter[date] = Counter()
    per_time: Counter[str] = Counter()
    booked_by_doctor: Counter[int] = Counter()
    cancelled_by_doctor: Counter[int] = Counter()

    for doctor_id, slot_start, status in rows:
        by_status[status] = by_status.get(status, 0) + 1
        if status == cancelled_value:
            cancelled_by_doctor[doctor_id] += 1
            continue
        local = as_utc(slot_start).astimezone(tz)
        per_day[local.date()] += 1
        per_time[local.strftime("%H:%M")] += 1
        booked_by_doctor[doctor_id] += 1

    total = len(rows)
    days = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]
    busiest = sorted(per_time.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_SLOTS]

    doctors = db.execute(select(Doctor, User).join(User, User.id == Doctor.user_id)).all()
    per_doctor = [
        DoctorStats(
            doctor_id=d.id,
            doctor_name=u.name,
            specialty=d.specialty,
            active=d.is_active,
            booked=booked_by_doctor[d.id],
            cancelled=cancelled_by_doctor[d.id],
        )
        for d, u in doctors
    ]
    per_doctor.sort(key=lambda x: (-x.booked, x.doctor_name))

    return StatsOut(
        from_date=from_date,
        to_date=to_date,
        timezone=tz_name,
        total_appointments=total,
        by_status=by_status,
        cancellation_rate=round(by_status[cancelled_value] / total, 4) if total else 0.0,
        bookings_per_day=[DayCount(date=d, booked=per_day[d]) for d in days],
        busiest_slots=[SlotCount(time=t, booked=c) for t, c in busiest],
        per_doctor=per_doctor,
    )
