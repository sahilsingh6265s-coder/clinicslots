from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScheduleItem(BaseModel):
    appointment_id: int
    patient_name: str
    slot_start: datetime
    slot_end: datetime
    status: str


class StatusUpdate(BaseModel):
    # A doctor can only close an appointment as completed or no_show.
    status: Literal["completed", "no_show"]
