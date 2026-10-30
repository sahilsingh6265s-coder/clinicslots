from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import Role, User

TZ = ZoneInfo(settings.clinic_timezone)

DOCTOR = {
    "name": "Dr. Rao",
    "email": "rao@example.com",
    "password": "doctorpass1",
    "specialty": "Cardiology",
    "slot_minutes": 30,
}
MONDAY_MORNING = [{"weekday": 0, "start_time": "10:00:00", "end_time": "12:00:00"}]


def create_user(db, email, password, role, name="Test User"):
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_headers(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def next_weekday(weekday: int) -> date:
    """A future date on the given weekday, at least 2 days ahead in the clinic's timezone."""
    today = datetime.now(TZ).date()
    days = ((weekday - today.weekday()) % 7) or 7
    if days < 2:
        days += 7
    return today + timedelta(days=days)


def iso_slot(day: date, hour: int, minute: int = 0) -> str:
    """e.g. '2030-01-07T10:00:00+05:30' (clinic-local time with offset)."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()


def admin_headers(client, db):
    create_user(db, "admin@example.com", "adminpass1", Role.admin.value, "Admin")
    return login_headers(client, "admin@example.com", "adminpass1")


def patient_headers(client, db, email="pat@example.com", name="Pat"):
    user = create_user(db, email, "patientpass1", Role.patient.value, name)
    return login_headers(client, email, "patientpass1"), user


def setup_doctor(client, db, windows=None):
    """Admin creates a doctor, doctor sets availability. Returns (doctor_id, doctor_headers, admin_headers)."""
    admin = admin_headers(client, db)
    doctor = client.post("/admin/doctors", json=DOCTOR, headers=admin)
    assert doctor.status_code == 201, doctor.text
    headers = login_headers(client, DOCTOR["email"], DOCTOR["password"])
    r = client.put("/doctor/availability", json=windows or MONDAY_MORNING, headers=headers)
    assert r.status_code == 200, r.text
    return doctor.json()["id"], headers, admin


def book_slot(client, headers, doctor_id, slot_iso):
    return client.post("/appointments", json={"doctor_id": doctor_id, "slot_start": slot_iso}, headers=headers)


def add_second_doctor(client, admin, email="sen@example.com", name="Dr. Sen", specialty="Dermatology"):
    """Admin creates another doctor with a Monday-morning schedule. Returns (doctor_id, headers)."""

    body = {**DOCTOR, "name": name, "email": email, "specialty": specialty}
    r = client.post("/admin/doctors", json=body, headers=admin)
    assert r.status_code == 201, r.text
    headers = login_headers(client, email, DOCTOR["password"])
    assert client.put("/doctor/availability", json=MONDAY_MORNING, headers=headers).status_code == 200
    return r.json()["id"], headers
