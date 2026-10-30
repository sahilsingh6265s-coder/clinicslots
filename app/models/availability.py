from datetime import time

from sqlalchemy import ForeignKey, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Availability(Base):
    """A doctor's working window on one weekday (0 = Monday ... 6 = Sunday)."""

    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    weekday: Mapped[int]
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
