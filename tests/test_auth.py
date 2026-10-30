from app.core.security import hash_password
from app.models.user import Role, User

SIGNUP = {"name": "Asha", "email": "asha@example.com", "password": "strongpass1"}


def signup(client, **overrides):
    return client.post("/auth/signup", json={**SIGNUP, **overrides})


def login(client, email="asha@example.com", password="strongpass1"):
    return client.post("/auth/login", data={"username": email, "password": password})


def auth_header(client, **kwargs):
    token = login(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_patient(client):
    r = signup(client)
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "patient"
    assert "password" not in body and "password_hash" not in body


def test_signup_duplicate_email_returns_409(client):
    signup(client)
    assert signup(client).status_code == 409


def test_signup_email_is_case_insensitive(client):
    signup(client)
    assert signup(client, email="ASHA@example.com").status_code == 409


def test_signup_short_password_rejected(client):
    assert signup(client, password="short").status_code == 422


def test_login_success_returns_token(client):
    signup(client)
    r = login(client)
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_login_wrong_password_returns_401(client):
    signup(client)
    assert login(client, password="wrongpass1").status_code == 401


def test_login_unknown_user_returns_401(client):
    assert login(client, email="nobody@example.com").status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_returns_current_user(client):
    signup(client)
    r = client.get("/auth/me", headers=auth_header(client))
    assert r.status_code == 200
    assert r.json()["email"] == "asha@example.com"


def test_patient_cannot_access_admin_route(client):
    signup(client)
    r = client.get("/admin/ping", headers=auth_header(client))
    assert r.status_code == 403


def test_admin_can_access_admin_route(client, db_session):
    db_session.add(
        User(name="Boss", email="admin@example.com",
             password_hash=hash_password("adminpass1"), role=Role.admin.value)
    )
    db_session.commit()
    headers = auth_header(client, email="admin@example.com", password="adminpass1")
    r = client.get("/admin/ping", headers=headers)
    assert r.status_code == 200
