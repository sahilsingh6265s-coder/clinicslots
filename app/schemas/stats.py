from datetime import date

from pydantic import BaseModel


class DayCount(BaseModel):
    date: date
    booked: int


class SlotCount(BaseModel):
    time: str  # local time of day, e.g. "10:30"
    booked: int


class DoctorStats(BaseModel):
    doctor_id: int
    doctor_name: str
    specialty: str
    active: bool
    booked: int
    cancelled: int


class StatsOut(BaseModel):
    from_date: date
    to_date: date
    timezone: str
    total_appointments: int  # every appointment in the range, including cancelled
    by_status: dict[str, int]
    cancellation_rate: float
    bookings_per_day: list[DayCount]  # "booked" = not cancelled
    busiest_slots: list[SlotCount]
    per_doctor: list[DoctorStats]
