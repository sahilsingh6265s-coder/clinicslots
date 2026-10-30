from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.schedule import ScheduleItem
from app.services.booking_service import AppointmentNotFound, NotChangeable
from app.services.slot_service import as_utc


class TooEarly(Exception):
    """The appointment has not started yet, so it cannot be closed."""


def get_schedule(db: Session, doctor: Doctor, day: date, tz: ZoneInfo) -> list[ScheduleItem]:
    """The doctor's appointments for one clinic-local day (cancelled ones hidden), earliest first."""
    day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    rows = db.execute(
        select(Appointment, User.name)
        .join(User, User.id == Appointment.patient_id)
        .where(
            Appointment.doctor_id == doctor.id,
            Appointment.slot_start >= day_start,
            Appointment.slot_start < day_end,
            Appointment.status != AppointmentStatus.cancelled.value,
        )
        .order_by(Appointment.slot_start)
    ).all()
    items = []
    for appointment, patient_name in rows:
        start = as_utc(appointment.slot_start).astimezone(tz)
        items.append(
            ScheduleItem(
                appointment_id=appointment.id,
                patient_name=patient_name,
                slot_start=start,
                slot_end=start + timedelta(minutes=doctor.slot_minutes),
                status=appointment.status,
            )
        )
    return items


def set_status(db: Session, doctor: Doctor, appointment_id: int, new_status: str, tz: ZoneInfo) -> ScheduleItem:
    """confirmed -> completed / no_show, only for this doctor's own appointments, only after it started."""
    appointment = db.get(Appointment, appointment_id)
    # Same error for "doesn't exist" and "belongs to another doctor".
    if appointment is None or appointment.doctor_id != doctor.id:
        raise AppointmentNotFound()
    if appointment.status != AppointmentStatus.confirmed.value:
        raise NotChangeable(f"Appointment is already {appointment.status}")
    if as_utc(appointment.slot_start) > datetime.now(timezone.utc):
        raise TooEarly("The appointment has not started yet")

    appointment.status = new_status
    db.commit()
    db.refresh(appointment)
    patient = db.get(User, appointment.patient_id)
    start = as_utc(appointment.slot_start).astimezone(tz)
    return ScheduleItem(
        appointment_id=appointment.id,
        patient_name=patient.name,
        slot_start=start,
        slot_end=start + timedelta(minutes=doctor.slot_minutes),
        status=appointment.status,
    )
