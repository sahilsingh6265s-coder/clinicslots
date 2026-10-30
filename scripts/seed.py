"""Fill the database with fake demo data (doctors, patients, appointments).

    python -m scripts.seed                 # only works on an EMPTY database
    python -m scripts.seed --reset         # wipe ALL data first (asks you to type YES)
    python -m scripts.seed --reset --yes   # same, without the question

Everything here is fake (Faker library). Every seeded account uses the same
demo password, printed at the end. Never run this against real data.
"""
import argparse
import random
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from faker import Faker
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import Availability
from app.models.doctor import Doctor
from app.models.user import Role, User
from app.schemas.auth import SignupRequest
from app.schemas.doctor import AvailabilityIn, DoctorCreate
from app.services import auth_service, booking_service, doctor_service
from app.services.slot_service import generate_slots, get_free_slots

DEMO_PASSWORD = "Password123"
ADMIN_EMAIL = "admin@clinicslot.demo"
SPECIALTIES = [
    "Cardiology", "Dermatology", "Pediatrics", "Orthopedics", "General Medicine",
    "ENT", "Neurology", "Gynecology", "Ophthalmology", "Psychiatry",
]
LONG_AGO = datetime(2000, 1, 1, tzinfo=timezone.utc)


class AlreadySeeded(Exception):
    pass


def _windows_for(db: Session, doctor_id: int, day):
    return [
        (a.start_time, a.end_time)
        for a in db.scalars(
            select(Availability).where(Availability.doctor_id == doctor_id, Availability.weekday == day.weekday())
        )
    ]


def wipe(db: Session) -> None:
    """Delete everything, children first (foreign keys)."""
    for model in (Appointment, Availability, Doctor, User):
        db.execute(delete(model))
    db.commit()


def seed(db: Session, n_doctors: int = 10, n_patients: int = 20, rng_seed: int = 42) -> dict:
    """Create the demo data. Raises AlreadySeeded if any user exists."""
    if db.scalar(select(func.count()).select_from(User)):
        raise AlreadySeeded("The database already has users. Use --reset to wipe it first.")

    rng = random.Random(rng_seed)
    fake = Faker("en_IN")
    Faker.seed(rng_seed)
    tz = ZoneInfo(settings.clinic_timezone)
    today = datetime.now(tz).date()

    # --- admin ---
    db.add(User(name="Clinic Admin", email=ADMIN_EMAIL, password_hash=hash_password(DEMO_PASSWORD), role=Role.admin.value))
    db.commit()

    # --- doctors, created the same way the admin API does it ---
    doctor_ids = []
    for i in range(n_doctors):
        name = "Dr. " + fake.name()
        created = doctor_service.create_doctor(
            db,
            DoctorCreate(
                name=name,
                email=f"doctor{i + 1}@clinicslot.demo",
                password=DEMO_PASSWORD,
                specialty=SPECIALTIES[i % len(SPECIALTIES)],
                slot_minutes=rng.choice([15, 20, 30]),
            ),
        )
        doctor_ids.append(created.id)
        # 4-5 working weekdays, a morning window and (usually) an afternoon one
        weekdays = sorted(rng.sample(range(0, 6), rng.choice([4, 5])))
        windows = []
        for wd in weekdays:
            windows.append(AvailabilityIn(weekday=wd, start_time=time(9, 0), end_time=time(13, 0)))
            if rng.random() < 0.7:
                windows.append(AvailabilityIn(weekday=wd, start_time=time(15, 0), end_time=time(18, 0)))
        doctor_service.replace_availability(db, db.get(Doctor, created.id), windows)

    # --- patients ---
    patients = []
    for i in range(n_patients):
        patients.append(
            auth_service.register_patient(
                db,
                SignupRequest(name=fake.name(), email=f"patient{i + 1}@clinicslot.demo", password=DEMO_PASSWORD),
            )
        )

    doctors = [db.get(Doctor, d) for d in doctor_ids]

    # --- upcoming appointments, booked through the real booking service ---
    upcoming = cancelled_upcoming = 0
    for patient in patients:
        for _ in range(rng.randint(0, 3)):
            doctor = rng.choice(doctors)
            day = today + timedelta(days=rng.randint(1, 14))
            free = _free_slots_utc(db, doctor, day, tz)
            if not free:
                continue
            try:
                appt = booking_service.book_appointment(db, patient, doctor.id, rng.choice(free))
            except (booking_service.SlotTaken, booking_service.InvalidSlot):
                continue
            upcoming += 1
            if rng.random() < 0.15:
                booking_service.cancel_appointment(db, patient, appt.id)
                cancelled_upcoming += 1

    # --- history for the last 30 days (so the admin dashboard has numbers) ---
    used: set[tuple[int, datetime]] = set()
    past = 0
    for _ in range(90):
        doctor = rng.choice(doctors)
        day = today - timedelta(days=rng.randint(1, 30))
        windows = _windows_for(db, doctor.id, day)
        slots = generate_slots(day, windows, doctor.slot_minutes, set(), LONG_AGO, tz)
        if not slots:
            continue
        start = rng.choice(slots)[0].astimezone(timezone.utc)
        if (doctor.id, start) in used:
            continue
        used.add((doctor.id, start))
        status = rng.choices(
            [AppointmentStatus.completed.value, AppointmentStatus.no_show.value, AppointmentStatus.cancelled.value],
            weights=[70, 10, 20],
        )[0]
        db.add(Appointment(patient_id=rng.choice(patients).id, doctor_id=doctor.id, slot_start=start, status=status))
        past += 1
    db.commit()

    return {
        "doctors": len(doctors),
        "patients": len(patients),
        "upcoming_appointments": upcoming,
        "cancelled_upcoming": cancelled_upcoming,
        "past_appointments": past,
    }


def _free_slots_utc(db: Session, doctor: Doctor, day, tz):
    """Free future slot start times (UTC) for one doctor on one day."""
    return [s.astimezone(timezone.utc) for s, _ in get_free_slots(db, doctor.id, doctor.slot_minutes, day, tz)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed ClinicSlot with fake demo data.")
    parser.add_argument("--reset", action="store_true", help="delete ALL existing data first")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation with --reset")
    args = parser.parse_args()

    target = engine.url.render_as_string(hide_password=True)
    with SessionLocal() as db:
        if args.reset:
            if not args.yes:
                answer = input(f"This will DELETE ALL DATA in:\n  {target}\nType YES to continue: ")
                if answer.strip() != "YES":
                    print("Cancelled. Nothing was changed.")
                    return
            wipe(db)
        try:
            summary = seed(db)
        except AlreadySeeded as exc:
            print(exc)
            sys.exit(1)

    print(f"Seeded {target}")
    for key, value in summary.items():
        print(f"  {key.replace('_', ' ')}: {value}")
    print("\nDemo logins (all use the same password):")
    print(f"  password : {DEMO_PASSWORD}")
    print(f"  admin    : {ADMIN_EMAIL}")
    print("  doctor   : doctor1@clinicslot.demo ... doctor10@clinicslot.demo")
    print("  patient  : patient1@clinicslot.demo ... patient20@clinicslot.demo")


if __name__ == "__main__":
    main()
