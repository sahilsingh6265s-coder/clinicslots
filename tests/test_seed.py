import pytest
from sqlalchemy import func, select

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.user import Role, User
from scripts.seed import ADMIN_EMAIL, DEMO_PASSWORD, AlreadySeeded, seed, wipe
from tests.helpers import create_user, login_headers


def test_seed_creates_a_working_demo_database(client, db_session):
    summary = seed(db_session, n_doctors=4, n_patients=6)

    assert summary["doctors"] == 4 and summary["patients"] == 6
    assert db_session.scalar(select(func.count()).select_from(Doctor)) == 4
    assert db_session.scalar(select(func.count()).select_from(User)) == 1 + 4 + 6
    assert db_session.scalar(select(func.count()).select_from(Appointment)) > 0

    # the seeded accounts really work through the API
    patient = login_headers(client, "patient1@clinicslot.demo", DEMO_PASSWORD)
    assert len(client.get("/doctors", headers=patient).json()) == 4
    admin = login_headers(client, ADMIN_EMAIL, DEMO_PASSWORD)
    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["total_appointments"] > 0 and len(stats["per_doctor"]) == 4
    doctor = login_headers(client, "doctor1@clinicslot.demo", DEMO_PASSWORD)
    assert client.get("/doctor/availability", headers=doctor).json() != []


def test_seed_refuses_to_run_on_a_database_with_data(db_session):
    create_user(db_session, "someone@example.com", "password123", Role.patient.value)
    with pytest.raises(AlreadySeeded):
        seed(db_session, n_doctors=1, n_patients=1)
    assert db_session.scalar(select(func.count()).select_from(User)) == 1  # untouched


def test_wipe_then_seed_again(db_session):
    seed(db_session, n_doctors=2, n_patients=2)
    wipe(db_session)
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    seed(db_session, n_doctors=2, n_patients=2)  # allowed again after a wipe
    assert db_session.scalar(select(func.count()).select_from(Doctor)) == 2
