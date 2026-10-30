from datetime import date as date_type, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_doctor
from app.models.doctor import Doctor
from app.schemas.doctor import AvailabilityIn, AvailabilityOut
from app.schemas.schedule import ScheduleItem, StatusUpdate
from app.services import booking_service, doctor_service, schedule_service

router = APIRouter(prefix="/doctor", tags=["doctor"])


@router.get("/availability", response_model=list[AvailabilityOut])
def my_availability(doctor: Doctor = Depends(get_current_doctor), db: Session = Depends(get_db)):
    return doctor_service.get_availability(db, doctor)


@router.put("/availability", response_model=list[AvailabilityOut])
def set_my_availability(
    windows: list[AvailabilityIn],
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    """Replace the whole weekly schedule. Send [] to clear it."""
    try:
        return doctor_service.replace_availability(db, doctor, windows)
    except doctor_service.InvalidAvailability as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/schedule", response_model=list[ScheduleItem])
def my_schedule(
    date: date_type | None = None,
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    """The day's appointments (default: today in the clinic's timezone), earliest first."""
    tz = ZoneInfo(settings.clinic_timezone)
    return schedule_service.get_schedule(db, doctor, date or datetime.now(tz).date(), tz)


@router.patch("/appointments/{appointment_id}/status", response_model=ScheduleItem)
def update_appointment_status(
    appointment_id: int,
    data: StatusUpdate,
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db),
):
    """Close one of my appointments as completed or no_show (only after it has started)."""
    tz = ZoneInfo(settings.clinic_timezone)
    try:
        return schedule_service.set_status(db, doctor, appointment_id, data.status, tz)
    except booking_service.AppointmentNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    except (booking_service.NotChangeable, schedule_service.TooEarly) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
