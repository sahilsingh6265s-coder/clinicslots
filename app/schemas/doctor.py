from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class DoctorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    specialty: str = Field(min_length=1, max_length=100)
    slot_minutes: int = Field(default=30, ge=5, le=120)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return v


class DoctorOut(BaseModel):
    id: int
    name: str
    specialty: str
    slot_minutes: int


class AvailabilityIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    weekday: int
    start_time: time
    end_time: time


class SlotOut(BaseModel):
    start: datetime
    end: datetime


class SlotsResponse(BaseModel):
    doctor_id: int
    date: date
    timezone: str
    slot_minutes: int
    slots: list[SlotOut]
