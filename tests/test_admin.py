from datetime import date, datetime, timedelta, timezone

from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from tests.helpers import (
    TZ,
    add_second_doctor,
    book_slot,
    iso_slot,
    next_weekday,
    patient_headers,
    setup_doctor,
)


def stats(client, admin, from_date, to_date):
    return client.get(f"/admin/stats?from_date={from_date}&to_date={to_date}", headers=admin)


def insert_local(db, doctor_id, patient_id, local_dt, status=AppointmentStatus.confirmed.value):
    db.add(
        Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            slot_start=local_dt.astimezone(timezone.utc),
            status=status,
        )
    )
    db.commit()


# ---------- stats ----------

def test_stats_counts_statuses_days_slots_and_doctors(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    a, _ = patient_headers(client, db_session, "a@example.com", "Asha")
    b, _ = patient_headers(client, db_session, "b@example.com", "Bala")
    c, _ = patient_headers(client, db_session, "c@example.com", "Chitra")
    day = next_weekday(0)
    book_slot(client, a, doctor_id, iso_slot(day, 10, 0))
    book_slot(client, b, doctor_id, iso_slot(day, 10, 30))
    cancelled = book_slot(client, c, doctor_id, iso_slot(day, 11, 0)).json()
    client.delete(f"/appointments/{cancelled['id']}", headers=c)

    r = stats(client, admin, day, day)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_appointments"] == 3
    assert body["by_status"] == {"confirmed": 2, "cancelled": 1, "completed": 0, "no_show": 0}
    assert body["cancellation_rate"] == 0.3333
    assert body["bookings_per_day"] == [{"date": str(day), "booked": 2}]  # cancelled not counted
    assert body["busiest_slots"] == [{"time": "10:00", "booked": 1}, {"time": "10:30", "booked": 1}]
    assert body["per_doctor"] == [
        {"doctor_id": doctor_id, "doctor_name": "Dr. Rao", "specialty": "Cardiology",
         "active": True, "booked": 2, "cancelled": 1}
    ]
    assert body["timezone"] == "Asia/Kolkata"


def test_stats_busiest_slots_sorted_by_count_then_time(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    other_id, _ = add_second_doctor(client, admin)
    a, _ = patient_headers(client, db_session, "a@example.com")
    b, _ = patient_headers(client, db_session, "b@example.com")
    c, _ = patient_headers(client, db_session, "c@example.com")
    day = next_weekday(0)
    # 10:30 is booked twice (two doctors), 10:00 once
    book_slot(client, a, doctor_id, iso_slot(day, 10, 30))
    book_slot(client, b, other_id, iso_slot(day, 10, 30))
    book_slot(client, c, doctor_id, iso_slot(day, 10, 0))
    slots = stats(client, admin, day, day).json()["busiest_slots"]
    assert slots == [{"time": "10:30", "booked": 2}, {"time": "10:00", "booked": 1}]


def test_stats_range_lists_every_day_including_empty_ones(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    book_slot(client, pat, doctor_id, iso_slot(day, 10, 0))
    body = stats(client, admin, day - timedelta(days=1), day + timedelta(days=1)).json()
    assert [d["booked"] for d in body["bookings_per_day"]] == [0, 1, 0]


def test_stats_empty_range_has_zeros_and_no_division_error(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    body = stats(client, admin, "2020-01-01", "2020-01-03").json()
    assert body["total_appointments"] == 0 and body["cancellation_rate"] == 0.0
    assert body["busiest_slots"] == []
    assert len(body["bookings_per_day"]) == 3
    assert body["per_doctor"][0]["booked"] == 0  # doctors are listed even with no activity


def test_stats_assigns_late_night_appointments_to_the_clinics_local_day(client, db_session):
    """23:30 IST and 00:30 IST are 1 hour apart in UTC, but belong to different local days."""
    doctor_id, _, admin = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    day = date(2030, 1, 7)
    insert_local(db_session, doctor_id, patient.id, datetime(2030, 1, 7, 23, 30, tzinfo=TZ))
    insert_local(db_session, doctor_id, patient.id, datetime(2030, 1, 8, 0, 30, tzinfo=TZ))
    body = stats(client, admin, day, day + timedelta(days=1)).json()
    assert body["bookings_per_day"] == [
        {"date": "2030-01-07", "booked": 1},
        {"date": "2030-01-08", "booked": 1},
    ]
    assert {s["time"] for s in body["busiest_slots"]} == {"23:30", "00:30"}


def test_stats_counts_completed_and_no_show(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    _, patient = patient_headers(client, db_session)
    day = date(2030, 1, 7)
    insert_local(db_session, doctor_id, patient.id, datetime(2030, 1, 7, 10, 0, tzinfo=TZ), "completed")
    insert_local(db_session, doctor_id, patient.id, datetime(2030, 1, 7, 10, 30, tzinfo=TZ), "no_show")
    body = stats(client, admin, day, day).json()
    assert body["by_status"]["completed"] == 1 and body["by_status"]["no_show"] == 1
    assert body["bookings_per_day"][0]["booked"] == 2  # both were real, non-cancelled bookings


def test_stats_default_range_works(client, db_session):
    _, _, admin = setup_doctor(client, db_session)
    r = client.get("/admin/stats", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert len(body["bookings_per_day"]) == 30
    assert body["to_date"] == datetime.now(TZ).date().isoformat()


def test_stats_rejects_bad_ranges(client, db_session):
    _, _, admin = setup_doctor(client, db_session)
    assert stats(client, admin, "2030-01-10", "2030-01-01").status_code == 422  # reversed
    assert stats(client, admin, "2028-01-01", "2030-01-01").status_code == 422  # > 366 days
    assert client.get("/admin/stats?from_date=banana", headers=admin).status_code == 422


def test_stats_is_admin_only(client, db_session):
    _, doc, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    assert client.get("/admin/stats", headers=pat).status_code == 403
    assert client.get("/admin/stats", headers=doc).status_code == 403
    assert client.get("/admin/stats").status_code == 401


# ---------- removing (deactivating) doctors ----------

def test_admin_removes_a_doctor(client, db_session):
    doctor_id, doc, admin = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    day = next_weekday(0)
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=admin).status_code == 204

    assert client.get("/doctors", headers=pat).json() == []                       # hidden from the list
    assert client.get(f"/doctors/{doctor_id}", headers=pat).status_code == 404
    assert client.get(f"/doctors/{doctor_id}/slots?date={day}", headers=pat).status_code == 404
    assert book_slot(client, pat, doctor_id, iso_slot(day, 10, 0)).status_code == 404  # cannot be booked
    assert client.get("/doctor/availability", headers=doc).status_code == 403          # portal locked
    # the row is kept (soft delete), just inactive
    assert db_session.get(Doctor, doctor_id).is_active is False


def test_cannot_remove_doctor_with_upcoming_appointments(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    appt = book_slot(client, pat, doctor_id, iso_slot(next_weekday(0), 10, 0)).json()
    r = client.delete(f"/admin/doctors/{doctor_id}", headers=admin)
    assert r.status_code == 409 and "upcoming" in r.json()["detail"]
    assert db_session.get(Doctor, doctor_id).is_active is True

    client.delete(f"/appointments/{appt['id']}", headers=pat)  # patient cancels...
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=admin).status_code == 204  # ...now it works


def test_removed_doctor_keeps_history_and_stats(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    pat, patient = patient_headers(client, db_session)
    insert_local(db_session, doctor_id, patient.id, datetime(2030, 1, 7, 10, 0, tzinfo=TZ), "completed")
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=admin).status_code == 204

    history = client.get("/me/appointments", headers=pat).json()
    assert history["total"] == 1 and history["items"][0]["doctor_name"] == "Dr. Rao"
    body = stats(client, admin, "2030-01-07", "2030-01-07").json()
    assert body["per_doctor"][0]["active"] is False and body["per_doctor"][0]["booked"] == 1


def test_remove_unknown_or_already_removed_doctor_404(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    assert client.delete("/admin/doctors/999", headers=admin).status_code == 404
    client.delete(f"/admin/doctors/{doctor_id}", headers=admin)
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=admin).status_code == 404


def test_other_doctors_are_unaffected_by_a_removal(client, db_session):
    doctor_id, _, admin = setup_doctor(client, db_session)
    other_id, _ = add_second_doctor(client, admin)
    pat, _ = patient_headers(client, db_session)
    client.delete(f"/admin/doctors/{doctor_id}", headers=admin)
    assert [d["id"] for d in client.get("/doctors", headers=pat).json()] == [other_id]


def test_only_admin_can_remove_doctors(client, db_session):
    doctor_id, doc, _ = setup_doctor(client, db_session)
    pat, _ = patient_headers(client, db_session)
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=pat).status_code == 403
    assert client.delete(f"/admin/doctors/{doctor_id}", headers=doc).status_code == 403
    assert client.delete(f"/admin/doctors/{doctor_id}").status_code == 401
