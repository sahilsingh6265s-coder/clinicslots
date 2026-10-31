import pytest
from sqlalchemy import func, select

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.user import Role, User
from scripts.seed import (
    ADMIN_EMAIL,
    DEMO_PASSWORD,
    AlreadySeeded,
    resolve_admin_password,
    seed,
    wipe,
)
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


# ---------- private admin password ----------

def test_private_admin_password_replaces_the_public_one(client, db_session):
    summary = seed(db_session, n_doctors=2, n_patients=2, admin_password="MyPrivateAdmin9")
    assert summary["admin_password_is_private"] is True

    # the private password works, the public demo password does NOT work for the admin
    ok = client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": "MyPrivateAdmin9"})
    assert ok.status_code == 200
    public = client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": DEMO_PASSWORD})
    assert public.status_code == 401
    # patients and doctors still use the demo password
    assert client.post("/auth/login", data={"username": "patient1@clinicslot.demo", "password": DEMO_PASSWORD}).status_code == 200
    assert client.post("/auth/login", data={"username": "doctor1@clinicslot.demo", "password": DEMO_PASSWORD}).status_code == 200


def test_default_admin_uses_the_demo_password(client, db_session):
    summary = seed(db_session, n_doctors=1, n_patients=1)
    assert summary["admin_password_is_private"] is False
    assert client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": DEMO_PASSWORD}).status_code == 200


@pytest.mark.parametrize("bad", ["short", "x" * 73, "é" * 40])  # too short, too long, 80 bytes
def test_invalid_admin_password_is_rejected_before_anything_is_written(db_session, bad):
    with pytest.raises(ValueError):
        seed(db_session, n_doctors=1, n_patients=1, admin_password=bad)
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_resolve_admin_password_environment_variable_wins():
    result = resolve_admin_password(False, environ={"SEED_ADMIN_PASSWORD": "FromTheEnv123"})
    assert result == "FromTheEnv123"


def test_resolve_admin_password_defaults_to_public():
    assert resolve_admin_password(False, environ={}) is None


def test_resolve_admin_password_prompts_twice_and_checks_they_match():
    answers = iter(["SamePassword1", "SamePassword1"])
    assert resolve_admin_password(True, environ={}, ask=lambda _prompt: next(answers)) == "SamePassword1"

    mismatch = iter(["SamePassword1", "different123"])
    with pytest.raises(ValueError, match="did not match"):
        resolve_admin_password(True, environ={}, ask=lambda _prompt: next(mismatch))


def test_resolve_admin_password_validates_what_was_typed():
    answers = iter(["abc", "abc"])
    with pytest.raises(ValueError, match="at least 8"):
        resolve_admin_password(True, environ={}, ask=lambda _prompt: next(answers))
