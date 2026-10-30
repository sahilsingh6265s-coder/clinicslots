from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import Availability
from app.models.doctor import Doctor
from app.models.user import Role, User
from app.schemas.doctor import AvailabilityIn, DoctorCreate, DoctorOut
from app.services.auth_service import EmailAlreadyRegistered


class InvalidAvailability(ValueError):
    pass


class DoctorNotFound(Exception):
    pass


class DoctorHasUpcomingAppointments(Exception):
    pass


def _to_out(doctor: Doctor, user: User) -> DoctorOut:
    return DoctorOut(
        id=doctor.id, name=user.name, specialty=doctor.specialty, slot_minutes=doctor.slot_minutes
    )


def create_doctor(db: Session, data: DoctorCreate) -> DoctorOut:
    """Create the login account and the doctor profile in ONE transaction."""
    user = User(
        name=data.name.strip(),
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        role=Role.doctor.value,
    )
    db.add(user)
    try:
        db.flush()  # assigns user.id; fails here if the email already exists
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered()
    doctor = Doctor(user_id=user.id, specialty=data.specialty.strip(), slot_minutes=data.slot_minutes)
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return _to_out(doctor, user)


def list_doctors(db: Session, specialty: str | None = None) -> list[DoctorOut]:
    query = (
        select(Doctor, User)
        .join(User, User.id == Doctor.user_id)
        .where(Doctor.is_active.is_(True))
        .order_by(User.name)
    )
    if specialty:
        query = query.where(func.lower(Doctor.specialty) == specialty.strip().lower())
    return [_to_out(d, u) for d, u in db.execute(query).all()]


def get_doctor(db: Session, doctor_id: int) -> DoctorOut | None:
    row = db.execute(
        select(Doctor, User)
        .join(User, User.id == Doctor.user_id)
        .where(Doctor.id == doctor_id, Doctor.is_active.is_(True))
    ).first()
    return _to_out(*row) if row else None


def validate_windows(windows: list[AvailabilityIn], slot_minutes: int) -> None:
    """Each window must fit one slot, and windows on the same day must not overlap."""
    for w in windows:
        minutes = (
            datetime.combine(date.min, w.end_time) - datetime.combine(date.min, w.start_time)
        ).total_seconds() / 60
        if minutes < slot_minutes:
            raise InvalidAvailability(
                f"A window on weekday {w.weekday} is shorter than one {slot_minutes}-minute slot"
            )
    ordered = sorted(windows, key=lambda w: (w.weekday, w.start_time))
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.weekday == nxt.weekday and nxt.start_time < prev.end_time:
            raise InvalidAvailability(f"Overlapping windows on weekday {prev.weekday}")


def replace_availability(db: Session, doctor: Doctor, windows: list[AvailabilityIn]) -> list[Availability]:
    """Replace the whole weekly schedule atomically (delete old rows, insert new)."""
    validate_windows(windows, doctor.slot_minutes)
    db.execute(delete(Availability).where(Availability.doctor_id == doctor.id))
    rows = [
        Availability(
            doctor_id=doctor.id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time
        )
        for w in windows
    ]
    db.add_all(rows)
    db.commit()
    return get_availability(db, doctor)


def get_availability(db: Session, doctor: Doctor) -> list[Availability]:
    return list(
        db.scalars(
            select(Availability)
            .where(Availability.doctor_id == doctor.id)
            .order_by(Availability.weekday, Availability.start_time)
        ).all()
    )


def remove_doctor(db: Session, doctor_id: int) -> None:
    """Deactivate a doctor (soft delete). Refused while they have upcoming confirmed appointments."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise DoctorNotFound()
    upcoming = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.doctor_id == doctor.id,
            Appointment.status == AppointmentStatus.confirmed.value,
            Appointment.slot_start > datetime.now(timezone.utc),
        )
    )
    if upcoming:
        raise DoctorHasUpcomingAppointments(f"Doctor has {upcoming} upcoming confirmed appointment(s)")
    doctor.is_active = False
    db.commit()
