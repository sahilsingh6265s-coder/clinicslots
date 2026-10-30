from datetime import date, timedelta

from app.core.security import hash_password
from app.models.user import User


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
    """The next future date (1-7 days ahead) that falls on the given weekday."""
    today = date.today()
    return today + timedelta(days=((weekday - today.weekday()) % 7) or 7)
