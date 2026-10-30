"""Proof that the database, not application code, prevents double booking."""
import threading
from datetime import datetime, time, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import Availability
from app.models.doctor import Doctor
from app.models.user import Role, User
from app.services import booking_service
from tests.helpers import TZ, next_weekday



CONFIRMED = AppointmentStatus.confirmed.value
CANCELLED = AppointmentStatus.cancelled.value


def _slot(day, hour=10):
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=TZ).astimezone(timezone.utc)


def _seed_doctor_and_patients(engine, n_patients):
    shared_hash = hash_password("patientpass1")  # hash once; hashing is slow
    with Session(bind=engine) as db:
        doc_user = User(name="Dr. Rao", email="rao@example.com", password_hash=shared_hash, role=Role.doctor.value)
        db.add(doc_user)
        db.flush()
        doctor = Doctor(user_id=doc_user.id, specialty="Cardiology", slot_minutes=30)
        db.add(doctor)
        db.flush()
        db.add(Availability(doctor_id=doctor.id, weekday=0, start_time=time(10, 0), end_time=time(12, 0)))
        patients = [
            User(name=f"P{i}", email=f"p{i}@example.com", password_hash=shared_hash, role=Role.patient.value)
            for i in range(n_patients)
        ]
        db.add_all(patients)
        db.commit()
        return doctor.id, [p.id for p in patients]


def test_many_simultaneous_bookings_exactly_one_wins(concurrent_engine):
    n = 8
    doctor_id, patient_ids = _seed_doctor_and_patients(concurrent_engine, n)
    slot = _slot(next_weekday(0))
    barrier = threading.Barrier(n)  # make every thread fire at the same moment
    results, lock = [], threading.Lock()

    def worker(patient_id):
        with Session(bind=concurrent_engine) as db:  # each thread has its own session/connection
            patient = db.get(User, patient_id)
            barrier.wait()
            try:
                booking_service.book_appointment(db, patient, doctor_id, slot)
                outcome = "booked"
            except booking_service.SlotTaken:
                outcome = "taken"
            except Exception as exc:  # anything else is a bug
                outcome = f"error: {exc!r}"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(pid,)) for pid in patient_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("booked") == 1, results
    assert results.count("taken") == n - 1, results
    with Session(bind=concurrent_engine) as db:
        confirmed = db.query(Appointment).filter_by(doctor_id=doctor_id, status=CONFIRMED).count()
    assert confirmed == 1


def _add(db, doctor_id, patient_id, slot, status):
    db.add(Appointment(patient_id=patient_id, doctor_id=doctor_id, slot_start=slot, status=status))
    db.flush()


def test_constraint_rejects_two_confirmed_for_same_slot(engine):
    doctor_id, patients = _seed_doctor_and_patients(engine, 2)
    slot = _slot(next_weekday(0))
    with Session(bind=engine) as db:
        _add(db, doctor_id, patients[0], slot, CONFIRMED)
        with pytest.raises(IntegrityError):
            _add(db, doctor_id, patients[1], slot, CONFIRMED)


def test_constraint_allows_cancelled_rows_beside_a_confirmed_one(engine):
    doctor_id, patients = _seed_doctor_and_patients(engine, 2)
    slot = _slot(next_weekday(0))
    with Session(bind=engine) as db:
        _add(db, doctor_id, patients[0], slot, CANCELLED)
        _add(db, doctor_id, patients[1], slot, CANCELLED)
        _add(db, doctor_id, patients[1], slot, CONFIRMED)  # a new booking is fine
        db.commit()


def test_constraint_is_per_doctor_and_per_slot(engine):
    doctor_id, patients = _seed_doctor_and_patients(engine, 2)
    day = next_weekday(0)
    with Session(bind=engine) as db:
        _add(db, doctor_id, patients[0], _slot(day, 10), CONFIRMED)
        _add(db, doctor_id, patients[1], _slot(day, 11), CONFIRMED)  # different time: fine
        db.commit()
