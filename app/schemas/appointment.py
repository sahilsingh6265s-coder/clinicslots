from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field


class AppointmentCreate(BaseModel):
    doctor_id: int
    # AwareDatetime rejects times without a timezone offset, e.g. "2026-11-02T10:00:00+05:30"
    slot_start: AwareDatetime


class AppointmentReschedule(BaseModel):
    slot_start: AwareDatetime


class AppointmentOut(BaseModel):
    id: int
    doctor_id: int
    doctor_name: str
    specialty: str
    slot_start: datetime
    slot_end: datetime
    status: str
    created_at: datetime


class AppointmentPage(BaseModel):
    items: list[AppointmentOut]
    total: int
    page: int = Field(ge=1)
    page_size: int
