from datetime import datetime, timedelta, timezone

from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import Role
from tests.helpers import (
    create_user,
    iso_slot,
    login_headers,
    next_weekday,
    patient_headers,
    setup_doctor,
)


def book(client, headers, doctor_id, slot_iso):
    return client.post("/appointments", json={"doctor_id": doctor_id, "slot_start": slot_iso}, headers=headers)


def slot_times(client, headers, doctor_id, day):
    slots = client.get(f"/doctors/{doctor_id}/slots?date={day}", headers=headers).json()["slots"]
    return [s["start"][11:16] for s in slots]


def two_patients(client, db):
    a, a_user = patient_headers(client, db, "a@example.com", "Asha")
    b, b_user = patient_headers(client, db, "b@example.com", "Bala")
    return a, a_user, b, b_user


# ---------- booking ----------

def test_book_success(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    r = book(client, pat, doctor_id, iso_slot(day, 10, 30))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["doctor_name"] == "Dr. Rao" and body["specialty"] == "Cardiology"
    assert body["slot_start"].startswith(f"{day}T10:30:00")
    assert body["slot_end"].startswith(f"{day}T11:00:00")


def test_booked_slot_disappears_from_slot_list(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    book(client, pat, doctor_id, iso_slot(day, 10, 30))
    assert slot_times(client, pat, doctor_id, day) == ["10:00", "11:00", "11:30"]


def test_two_patients_same_slot_second_gets_409(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    slot = iso_slot(next_weekday(0), 10, 0)
    assert book(client, a, doctor_id, slot).status_code == 201
    r = book(client, b, doctor_id, slot)
    assert r.status_code == 409
    assert r.json()["detail"] == "Slot already booked"


def test_same_patient_cannot_book_same_slot_twice(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    slot = iso_slot(next_weekday(0), 10, 0)
    assert book(client, pat, doctor_id, slot).status_code == 201
    assert book(client, pat, doctor_id, slot).status_code == 409


def test_slot_can_be_rebooked_after_cancel(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    slot = iso_slot(next_weekday(0), 10, 0)
    first = book(client, a, doctor_id, slot).json()
    assert client.delete(f"/appointments/{first['id']}", headers=a).status_code == 200
    assert book(client, b, doctor_id, slot).status_code == 201  # the partial index allows this


def test_book_past_slot_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    r = book(client, pat, doctor_id, "2020-01-06T10:00:00+05:30")  # a past Monday
    assert r.status_code == 422


def test_book_unaligned_time_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    assert book(client, pat, doctor_id, iso_slot(next_weekday(0), 10, 15)).status_code == 422


def test_book_outside_working_hours_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    assert book(client, pat, doctor_id, iso_slot(next_weekday(0), 9, 0)).status_code == 422
    assert book(client, pat, doctor_id, iso_slot(next_weekday(0), 12, 0)).status_code == 422  # window ends 12:00


def test_book_on_non_working_day_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    assert book(client, pat, doctor_id, iso_slot(next_weekday(1), 10, 0)).status_code == 422


def test_book_without_timezone_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    assert book(client, pat, doctor_id, f"{day}T10:00:00").status_code == 422


def test_book_unknown_doctor_404(client, db_session):
    pat, _ = patient_headers(client, db_session)
    assert book(client, pat, 999, iso_slot(next_weekday(0), 10, 0)).status_code == 404


def test_doctor_cannot_book_403(client, db_session):
    doctor_id, doctor_headers, _ = setup_doctor(client, db_session)
    assert book(client, doctor_headers, doctor_id, iso_slot(next_weekday(0), 10, 0)).status_code == 403


def test_book_requires_login(client, db_session):
    r = client.post("/appointments", json={"doctor_id": 1, "slot_start": "2030-01-07T10:00:00+05:30"})
    assert r.status_code == 401


# ---------- cancelling ----------

def test_cancel_own_appointment(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    appt = book(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.delete(f"/appointments/{appt['id']}", headers=pat)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert "10:00" in slot_times(client, pat, doctor_id, day)  # slot is free again


def test_cannot_cancel_someone_elses_appointment(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    appt = book(client, a, doctor_id, iso_slot(next_weekday(0), 10, 0)).json()
    assert client.delete(f"/appointments/{appt['id']}", headers=b).status_code == 404


def test_cancel_twice_409(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    appt = book(client, pat, doctor_id, iso_slot(next_weekday(0), 10, 0)).json()
    client.delete(f"/appointments/{appt['id']}", headers=pat)
    assert client.delete(f"/appointments/{appt['id']}", headers=pat).status_code == 409


def test_cancel_unknown_appointment_404(client, db_session):
    pat, _ = patient_headers(client, db_session)
    assert client.delete("/appointments/999", headers=pat).status_code == 404


def _insert_soon(db, doctor_id, patient_id, hours_from_now):
    """Insert a confirmed appointment starting soon (bypasses booking validation)."""
    appt = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=hours_from_now),
        status=AppointmentStatus.confirmed.value,
    )
    db.add(appt)
    db.commit()
    return appt.id


def test_cancel_inside_cutoff_409(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, user = patient_headers(client, db_session)
    soon = _insert_soon(db_session, doctor_id, user.id, hours_from_now=1)
    r = client.delete(f"/appointments/{soon}", headers=pat)
    assert r.status_code == 409 and "within" in r.json()["detail"]


def test_cancel_outside_cutoff_ok(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, user = patient_headers(client, db_session)
    later = _insert_soon(db_session, doctor_id, user.id, hours_from_now=5)
    assert client.delete(f"/appointments/{later}", headers=pat).status_code == 200


# ---------- rescheduling ----------

def test_reschedule_moves_appointment(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    old = book(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.patch(f"/appointments/{old['id']}", json={"slot_start": iso_slot(day, 11, 0)}, headers=pat)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] != old["id"] and new["status"] == "confirmed"
    assert new["slot_start"].startswith(f"{day}T11:00:00")
    # old slot is free again, new slot is taken
    assert slot_times(client, pat, doctor_id, day) == ["10:00", "10:30", "11:30"]
    history = client.get("/me/appointments", headers=pat).json()
    assert sorted(a["status"] for a in history["items"]) == ["cancelled", "confirmed"]


def test_reschedule_to_taken_slot_keeps_original(client, db_session):
    """Atomic: if the new slot is taken the patient must NOT lose their old appointment."""
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    day = next_weekday(0)
    book(client, b, doctor_id, iso_slot(day, 11, 0))
    mine = book(client, a, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.patch(f"/appointments/{mine['id']}", json={"slot_start": iso_slot(day, 11, 0)}, headers=a)
    assert r.status_code == 409
    items = client.get("/me/appointments", headers=a).json()["items"]
    assert len(items) == 1 and items[0]["status"] == "confirmed"
    assert items[0]["slot_start"].startswith(f"{day}T10:00:00")


def test_reschedule_to_same_slot_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    appt = book(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.patch(f"/appointments/{appt['id']}", json={"slot_start": iso_slot(day, 10, 0)}, headers=pat)
    assert r.status_code == 422


def test_reschedule_to_invalid_slot_422(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    appt = book(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.patch(f"/appointments/{appt['id']}", json={"slot_start": iso_slot(day, 15, 0)}, headers=pat)
    assert r.status_code == 422


def test_reschedule_someone_elses_appointment_404(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    day = next_weekday(0)
    appt = book(client, a, doctor_id, iso_slot(day, 10, 0)).json()
    r = client.patch(f"/appointments/{appt['id']}", json={"slot_start": iso_slot(day, 11, 0)}, headers=b)
    assert r.status_code == 404


def test_reschedule_cancelled_appointment_409(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    appt = book(client, pat, doctor_id, iso_slot(day, 10, 0)).json()
    client.delete(f"/appointments/{appt['id']}", headers=pat)
    r = client.patch(f"/appointments/{appt['id']}", json={"slot_start": iso_slot(day, 11, 0)}, headers=pat)
    assert r.status_code == 409


def test_reschedule_inside_cutoff_409(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, user = patient_headers(client, db_session)
    soon = _insert_soon(db_session, doctor_id, user.id, hours_from_now=1)
    r = client.patch(
        f"/appointments/{soon}", json={"slot_start": iso_slot(next_weekday(0), 10, 0)}, headers=pat
    )
    assert r.status_code == 409


# ---------- listing ----------

def _book_three(client, db, doctor_id, pat):
    day = next_weekday(0)
    return [book(client, pat, doctor_id, iso_slot(day, 10, m)).json() for m in (0, 30)] + [
        book(client, pat, doctor_id, iso_slot(day, 11, 0)).json()
    ]


def test_list_is_paginated(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    _book_three(client, db_session, doctor_id, pat)
    p1 = client.get("/me/appointments?page=1&page_size=2", headers=pat).json()
    p2 = client.get("/me/appointments?page=2&page_size=2", headers=pat).json()
    assert p1["total"] == 3 and len(p1["items"]) == 2
    assert len(p2["items"]) == 1
    assert p1["items"][0]["slot_start"] > p1["items"][1]["slot_start"]  # newest first


def test_list_status_filter(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    appts = _book_three(client, db_session, doctor_id, pat)
    client.delete(f"/appointments/{appts[0]['id']}", headers=pat)
    cancelled = client.get("/me/appointments?status=cancelled", headers=pat).json()
    confirmed = client.get("/me/appointments?status=confirmed", headers=pat).json()
    assert cancelled["total"] == 1 and confirmed["total"] == 2


def test_list_shows_only_own_appointments(client, db_session):
    doctor_id, _, _ = setup_doctor(client, db_session)
    a, _, b, _ = two_patients(client, db_session)
    book(client, a, doctor_id, iso_slot(next_weekday(0), 10, 0))
    assert client.get("/me/appointments", headers=b).json()["total"] == 0


def test_list_rejects_bad_params(client, db_session):
    pat, _ = patient_headers(client, db_session)
    assert client.get("/me/appointments?page_size=101", headers=pat).status_code == 422
    assert client.get("/me/appointments?page=0", headers=pat).status_code == 422
    assert client.get("/me/appointments?status=bogus", headers=pat).status_code == 422
