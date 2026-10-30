from sqlalchemy import ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    specialty: Mapped[str] = mapped_column(String(100), index=True)
    slot_minutes: Mapped[int] = mapped_column(default=30)
    # "Removing" a doctor deactivates them instead of deleting the row, so past
    # appointments (and the admin stats) keep pointing at a real doctor.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
