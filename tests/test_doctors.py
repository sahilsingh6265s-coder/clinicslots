from datetime import datetime, timezone

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import Role
from tests.helpers import (
    DOCTOR,
    MONDAY_MORNING,
    TZ,
    admin_headers,
    create_user,
    login_headers,
    next_weekday,
    setup_doctor,
)
from tests.helpers import patient_headers as _patient_headers


def patient_headers(client, db):
    return _patient_headers(client, db)[0]


# ---------- admin creates doctors ----------

def test_admin_can_create_doctor(client, db_session):
    r = client.post("/admin/doctors", json=DOCTOR, headers=admin_headers(client, db_session))
    assert r.status_code == 201
    assert r.json()["specialty"] == "Cardiology"
    # the new doctor can log in and has the doctor role
    headers = login_headers(client, DOCTOR["email"], DOCTOR["password"])
    assert client.get("/auth/me", headers=headers).json()["role"] == "doctor"


def test_patient_cannot_create_doctor(client, db_session):
    r = client.post("/admin/doctors", json=DOCTOR, headers=patient_headers(client, db_session))
    assert r.status_code == 403


def test_create_doctor_requires_login(client):
    assert client.post("/admin/doctors", json=DOCTOR).status_code == 401


def test_create_doctor_duplicate_email_409(client, db_session):
    admin = admin_headers(client, db_session)
    client.post("/admin/doctors", json=DOCTOR, headers=admin)
    assert client.post("/admin/doctors", json=DOCTOR, headers=admin).status_code == 409


# ---------- availability ----------

def test_doctor_sets_and_reads_availability(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    r = client.get("/doctor/availability", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1 and r.json()[0]["weekday"] == 0


def test_put_availability_replaces_old_schedule(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    new = [{"weekday": 2, "start_time": "09:00:00", "end_time": "10:00:00"}]
    client.put("/doctor/availability", json=new, headers=headers)
    result = client.get("/doctor/availability", headers=headers).json()
    assert [w["weekday"] for w in result] == [2]


def test_overlapping_windows_rejected(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    bad = [
        {"weekday": 0, "start_time": "10:00:00", "end_time": "12:00:00"},
        {"weekday": 0, "start_time": "11:00:00", "end_time": "13:00:00"},
    ]
    assert client.put("/doctor/availability", json=bad, headers=headers).status_code == 422


def test_end_before_start_rejected(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    bad = [{"weekday": 0, "start_time": "12:00:00", "end_time": "10:00:00"}]
    assert client.put("/doctor/availability", json=bad, headers=headers).status_code == 422


def test_window_shorter_than_one_slot_rejected(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    bad = [{"weekday": 0, "start_time": "10:00:00", "end_time": "10:15:00"}]
    assert client.put("/doctor/availability", json=bad, headers=headers).status_code == 422


def test_invalid_weekday_rejected(client, db_session):
    _, headers, _ = setup_doctor(client, db_session)
    bad = [{"weekday": 7, "start_time": "10:00:00", "end_time": "11:00:00"}]
    assert client.put("/doctor/availability", json=bad, headers=headers).status_code == 422


def test_patient_cannot_set_availability(client, db_session):
    r = client.put("/doctor/availability", json=MONDAY_MORNING, headers=patient_headers(client, db_session))
    assert r.status_code == 403


# ---------- browsing doctors ----------

def test_list_doctors_and_filter_by_specialty(client, db_session):
    _, _, admin = setup_doctor(client, db_session)
    other = {**DOCTOR, "name": "Dr. Sen", "email": "sen@example.com", "specialty": "Dermatology"}
    client.post("/admin/doctors", json=other, headers=admin)
    pat = patient_headers(client, db_session)

    assert len(client.get("/doctors", headers=pat).json()) == 2
    cardio = client.get("/doctors?specialty=cardiology", headers=pat).json()  # case-insensitive
    assert [d["name"] for d in cardio] == ["Dr. Rao"]


def test_get_unknown_doctor_404(client, db_session):
    assert client.get("/doctors/999", headers=patient_headers(client, db_session)).status_code == 404


def test_browsing_requires_login(client):
    assert client.get("/doctors").status_code == 401


# ---------- slots ----------

def test_slots_for_a_working_day(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat = patient_headers(client, db_session)
    day = next_weekday(0)  # a future Monday
    r = client.get(f"/doctors/{doctor_id}/slots?date={day}", headers=pat)
    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == settings.clinic_timezone
    assert len(body["slots"]) == 4  # 10:00, 10:30, 11:00, 11:30
    assert body["slots"][0]["start"].startswith(f"{day}T10:00:00")


def test_no_slots_on_a_non_working_day(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat = patient_headers(client, db_session)
    tuesday = next_weekday(1)
    r = client.get(f"/doctors/{doctor_id}/slots?date={tuesday}", headers=pat)
    assert r.json()["slots"] == []


def test_past_date_has_no_slots(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat = patient_headers(client, db_session)
    r = client.get(f"/doctors/{doctor_id}/slots?date=2020-01-06", headers=pat)  # a past Monday
    assert r.json()["slots"] == []


def _book(db, doctor_id, patient_id, day, hour, minute, status):
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
    db.add(
        Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            slot_start=local.astimezone(timezone.utc),
            status=status,
        )
    )
    db.commit()


def test_booked_slot_disappears_but_cancelled_one_does_not(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    patient = create_user(db_session, "p2@example.com", "patientpass1", Role.patient.value)
    pat = login_headers(client, "p2@example.com", "patientpass1")
    day = next_weekday(0)

    _book(db_session, doctor_id, patient.id, day, 10, 30, AppointmentStatus.confirmed.value)
    _book(db_session, doctor_id, patient.id, day, 11, 0, AppointmentStatus.cancelled.value)

    slots = client.get(f"/doctors/{doctor_id}/slots?date={day}", headers=pat).json()["slots"]
    times = [s["start"][11:16] for s in slots]
    assert times == ["10:00", "11:00", "11:30"]  # 10:30 booked; 11:00 was cancelled so it is free


def test_slots_unknown_doctor_404(client, db_session):
    pat = patient_headers(client, db_session)
    assert client.get("/doctors/999/slots?date=2030-01-07", headers=pat).status_code == 404


def test_slots_bad_date_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat = patient_headers(client, db_session)
    assert client.get(f"/doctors/{doctor_id}/slots?date=not-a-date", headers=pat).status_code == 422
