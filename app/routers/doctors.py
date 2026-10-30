from datetime import date as date_type
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.doctor import DoctorOut, SlotOut, SlotsResponse
from app.services import doctor_service, slot_service

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
def list_doctors(
    specialty: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return doctor_service.list_doctors(db, specialty)


@router.get("/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    doctor = doctor_service.get_doctor(db, doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return doctor


@router.get("/{doctor_id}/slots", response_model=SlotsResponse)
def get_slots(
    doctor_id: int,
    date: date_type = Query(description="YYYY-MM-DD, in the clinic's timezone"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    doctor = doctor_service.get_doctor(db, doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    tz = ZoneInfo(settings.clinic_timezone)
    slots = slot_service.get_free_slots(db, doctor.id, doctor.slot_minutes, date, tz)
    return SlotsResponse(
        doctor_id=doctor.id,
        date=date,
        timezone=settings.clinic_timezone,
        slot_minutes=doctor.slot_minutes,
        slots=[SlotOut(start=s, end=e) for s, e in slots],
    )
