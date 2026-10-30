from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_doctor
from app.models.doctor import Doctor
from app.schemas.doctor import AvailabilityIn, AvailabilityOut
from app.services import doctor_service

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
