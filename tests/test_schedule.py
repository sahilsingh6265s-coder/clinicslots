from datetime import datetime, timedelta, timezone

from app.models.appointment import Appointment, AppointmentStatus
from tests.helpers import (
    TZ,
    add_second_doctor,
    book_slot,
    iso_slot,
    next_weekday,
    patient_headers,
    setup_doctor,
)


def insert_started(db, doctor_id, patient_id, hours_ago=1, status=AppointmentStatus.confirmed.value):
    """An appointment that already started (bypasses booking validation, which forbids the past)."""
    appt = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_start=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        status=status,
    )
    db.add(appt)
    db.commit()
    return appt.id


# ---------- GET /doctor/schedule ----------

def test_schedule_lists_the_days_appointments_in_time_order(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    a, _ = patient_headers(client, db_session, "a@example.com", "Asha")
    b, _ = patient_headers(client, db_session, "b@example.com", "Bala")
    day = next_weekday(0)
    book_slot(client, b, doctor_id, iso_slot(day, 11, 0))  # booked first, but later in the day
    book_slot(client, a, doctor_id, iso_slot(day, 10, 0))

    r = client.get(f"/doctor/schedule?date={day}", headers=doc)
    assert r.status_code == 200
    items = r.json()
    assert [i["patient_name"] for i in items] == ["Asha", "Bala"]
    assert items[0]["slot_start"].startswith(f"{day}T10:00:00")
    assert items[0]["slot_end"].startswith(f"{day}T10:30:00")
    assert items[0]["status"] == "confirmed"


def test_schedule_hides_cancelled_appointments(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    appt = book_slot(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    client.delete(f"/appointments/{appt['id']}", headers=pat)
    assert client.get(f"/doctor/schedule?date={day}", headers=doc).json() == []


def test_schedule_for_another_day_is_empty(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    book_slot(client, pat, doctor_id, iso_slot(next_weekday(0), 10, 0))
    assert client.get(f"/doctor/schedule?date={next_weekday(1)}", headers=doc).json() == []


def test_schedule_defaults_to_today(client, db_session):
    _, doc, _ = setup_doctor(client, db_session)
    r = client.get("/doctor/schedule", headers=doc)
    assert r.status_code == 200 and r.json() == []


def test_schedule_only_shows_my_own_patients(client, db_session):
    doctor_id, doc, admin = setup_doctor(client, db_session)
    other_id, other_doc = add_second_doctor(client, admin)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    book_slot(client, pat, other_id, iso_slot(day, 10, 0))
    assert client.get(f"/doctor/schedule?date={day}", headers=doc).json() == []
    assert len(client.get(f"/doctor/schedule?date={day}", headers=other_doc).json()) == 1


def test_schedule_is_doctor_only(client, db_session):
    pat, _ = patient_headers(client, db_session)
    assert client.get("/doctor/schedule", headers=pat).status_code == 403
    assert client.get("/doctor/schedule").status_code == 401


def test_schedule_bad_date_422(client, db_session):
    _, doc, _ = setup_doctor(client, db_session)
    assert client.get("/doctor/schedule?date=banana", headers=doc).status_code == 422


# ---------- PATCH /doctor/appointments/{id}/status ----------

def test_doctor_marks_started_appointment_completed(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=doc)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed" and r.json()["patient_name"] == "Pat"


def test_doctor_marks_no_show(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "no_show"}, headers=doc)
    assert r.status_code == 200 and r.json()["status"] == "no_show"


def test_cannot_close_an_appointment_that_has_not_started(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    appt = book_slot(client, pat, doctor_id, iso_slot(next_weekday(0), 10, 0)).json()
    r = client.patch(f"/doctor/appointments/{appt['id']}/status", json={"status": "completed"}, headers=doc)
    assert r.status_code == 409 and "not started" in r.json()["detail"]


def test_cannot_close_the_same_appointment_twice(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id)
    client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=doc)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "no_show"}, headers=doc)
    assert r.status_code == 409


def test_cannot_close_a_cancelled_appointment(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id, status=AppointmentStatus.cancelled.value)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=doc)
    assert r.status_code == 409


def test_status_must_be_completed_or_no_show(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id)
    for bad in ("confirmed", "cancelled", "banana"):
        r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": bad}, headers=doc)
        assert r.status_code == 422, bad


def test_cannot_close_another_doctors_appointment(client, db_session):
    doctor_id, doc, admin = setup_doctor(client, db_session)
    other_id, other_doc = add_second_doctor(client, admin)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, other_id, patient.id)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=doc)
    assert r.status_code == 404


def test_close_unknown_appointment_404(client, db_session):
    _, doc, _ = setup_doctor(client, db_session)
    r = client.patch("/doctor/appointments/999/status", json={"status": "completed"}, headers=doc)
    assert r.status_code == 404


def test_patient_cannot_close_appointments(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id)
    r = client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=pat)
    assert r.status_code == 403


def test_closed_appointment_still_appears_on_the_schedule(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    appt_id = insert_started(db_session, doctor_id, patient.id, hours_ago=1)
    client.patch(f"/doctor/appointments/{appt_id}/status", json={"status": "completed"}, headers=doc)

    # ask for the appointment's own clinic-local date (robust around midnight)
    started_local = (datetime.now(timezone.utc) - timedelta(hours=1)).astimezone(TZ)
    items = client.get(f"/doctor/schedule?date={started_local.date()}", headers=doc).json()
    assert [(i["appointment_id"], i["status"]) for i in items] == [(appt_id, "completed")]
