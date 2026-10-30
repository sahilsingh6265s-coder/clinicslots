"""Create the first admin account.  Run from the project root:

    python -m scripts.create_admin
"""
import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User


def main() -> None:
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Password (min 8 chars): ")
    if not name or "@" not in email or len(password) < 8 or len(password.encode()) > 72:
        print("Invalid input: need a name, a valid email and a password of 8-72 characters.")
        return

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            print("A user with that email already exists.")
            return
        db.add(User(name=name, email=email, password_hash=hash_password(password), role=Role.admin.value))
        db.commit()
    print(f"Admin created: {email}")


if __name__ == "__main__":
    main()
