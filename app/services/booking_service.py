"""Booking, cancelling and rescheduling.

The key idea: we do NOT "check if the slot is free, then insert". Two requests
can both pass that check at the same instant. Instead we just INSERT and let the
database's partial unique index (see models/appointment.py) reject the loser.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import Availability
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.appointment import AppointmentOut, AppointmentPage
from app.services.slot_service import as_utc, generate_slots


class DoctorNotFound(Exception):
    pass


class AppointmentNotFound(Exception):
    pass


class InvalidSlot(Exception):
    """Slot is in the past, outside working hours, or not aligned to the slot grid."""


class SlotTaken(Exception):
    """Someone else already holds this slot."""


class NotChangeable(Exception):
    """Appointment is not confirmed (already cancelled, completed, ...)."""


class TooLateToChange(Exception):
    """Inside the cancellation cut-off window."""


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.clinic_timezone)


def _validate_slot(db: Session, doctor: Doctor, slot_start: datetime) -> datetime:
    """Return slot_start in UTC if it is a real, future, bookable slot; else raise InvalidSlot."""
    start_utc = as_utc(slot_start)
    day = start_utc.astimezone(_tz()).date()
    windows = [
        (a.start_time, a.end_time)
        for a in db.scalars(
            select(Availability).where(
                Availability.doctor_id == doctor.id, Availability.weekday == day.weekday()
            )
        )
    ]
    # Generate the day's slots with nothing booked: this checks working hours,
    # slot alignment and "not in the past" in one go.
    valid = generate_slots(day, windows, doctor.slot_minutes, set(), datetime.now(timezone.utc), _tz())
    if start_utc not in {s.astimezone(timezone.utc) for s, _ in valid}:
        raise InvalidSlot("That time is not an available slot for this doctor")
    return start_utc


def _check_changeable(appointment: Appointment) -> None:
    if appointment.status != AppointmentStatus.confirmed.value:
        raise NotChangeable(f"Appointment is already {appointment.status}")
    cutoff = timedelta(hours=settings.cancellation_cutoff_hours)
    if as_utc(appointment.slot_start) - datetime.now(timezone.utc) < cutoff:
        raise TooLateToChange(
            f"Appointments cannot be changed within {settings.cancellation_cutoff_hours} hours of the start time"
        )


def _own_appointment(db: Session, patient: User, appointment_id: int) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    # Same error whether it doesn't exist or belongs to someone else (don't leak existence).
    if appointment is None or appointment.patient_id != patient.id:
        raise AppointmentNotFound()
    return appointment


def to_out(db: Session, appointment: Appointment) -> AppointmentOut:
    doctor = db.get(Doctor, appointment.doctor_id)
    doctor_user = db.get(User, doctor.user_id)
    start = as_utc(appointment.slot_start).astimezone(_tz())
    return AppointmentOut(
        id=appointment.id,
        doctor_id=doctor.id,
        doctor_name=doctor_user.name,
        specialty=doctor.specialty,
        slot_start=start,
        slot_end=start + timedelta(minutes=doctor.slot_minutes),
        status=appointment.status,
        created_at=appointment.created_at,
    )


def book_appointment(db: Session, patient: User, doctor_id: int, slot_start: datetime) -> Appointment:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise DoctorNotFound()
    start_utc = _validate_slot(db, doctor, slot_start)

    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_start=start_utc,
        status=AppointmentStatus.confirmed.value,
    )
    db.add(appointment)
    try:
        db.commit()  # the database decides who wins a race
    except IntegrityError:
        db.rollback()
        raise SlotTaken()
    db.refresh(appointment)
    return appointment


def cancel_appointment(db: Session, patient: User, appointment_id: int) -> Appointment:
    """Soft cancel: keep the row (history) and free the slot by changing its status."""
    appointment = _own_appointment(db, patient, appointment_id)
    _check_changeable(appointment)
    appointment.status = AppointmentStatus.cancelled.value
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session, patient: User, appointment_id: int, new_slot_start: datetime
) -> Appointment:
    """Cancel the old appointment and create the new one in ONE transaction.

    If the new slot is taken, the whole transaction rolls back and the patient
    keeps the original appointment.
    """
    old = _own_appointment(db, patient, appointment_id)
    _check_changeable(old)
    doctor = db.get(Doctor, old.doctor_id)
    new_start = _validate_slot(db, doctor, new_slot_start)
    if new_start == as_utc(old.slot_start):
        raise InvalidSlot("Choose a different time from your current appointment")

    old.status = AppointmentStatus.cancelled.value
    new = Appointment(
        patient_id=patient.id,
        doctor_id=old.doctor_id,
        slot_start=new_start,
        status=AppointmentStatus.confirmed.value,
    )
    db.add(new)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise SlotTaken()
    db.refresh(new)
    return new


def list_my_appointments(
    db: Session, patient: User, page: int, page_size: int, status: str | None
) -> AppointmentPage:
    filters = [Appointment.patient_id == patient.id]
    if status:
        filters.append(Appointment.status == status)
    total = db.scalar(select(func.count()).select_from(Appointment).where(*filters)) or 0
    rows = db.scalars(
        select(Appointment)
        .where(*filters)
        .order_by(Appointment.slot_start.desc(), Appointment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AppointmentPage(
        items=[to_out(db, a) for a in rows], total=total, page=page, page_size=page_size
    )
