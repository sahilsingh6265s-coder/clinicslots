from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.appointment import AppointmentStatus
from app.models.user import Role, User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentPage,
    AppointmentReschedule,
)
from app.services import booking_service as svc

router = APIRouter(tags=["appointments"])

patient_only = require_roles(Role.patient.value)


def _http_error(exc: Exception) -> HTTPException:
    """Translate service-layer exceptions into HTTP responses."""
    if isinstance(exc, (svc.DoctorNotFound, svc.AppointmentNotFound)):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if isinstance(exc, svc.InvalidSlot):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, svc.SlotTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "Slot already booked")
    if isinstance(exc, (svc.NotChangeable, svc.TooLateToChange)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    raise exc


@router.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book(data: AppointmentCreate, db: Session = Depends(get_db), patient: User = Depends(patient_only)):
    try:
        appointment = svc.book_appointment(db, patient, data.doctor_id, data.slot_start)
    except (svc.DoctorNotFound, svc.InvalidSlot, svc.SlotTaken) as exc:
        raise _http_error(exc)
    return svc.to_out(db, appointment)


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
def reschedule(
    appointment_id: int,
    data: AppointmentReschedule,
    db: Session = Depends(get_db),
    patient: User = Depends(patient_only),
):
    """Move to another slot with the same doctor. Returns the NEW appointment."""
    try:
        appointment = svc.reschedule_appointment(db, patient, appointment_id, data.slot_start)
    except (svc.AppointmentNotFound, svc.InvalidSlot, svc.SlotTaken, svc.NotChangeable, svc.TooLateToChange) as exc:
        raise _http_error(exc)
    return svc.to_out(db, appointment)


@router.delete("/appointments/{appointment_id}", response_model=AppointmentOut)
def cancel(appointment_id: int, db: Session = Depends(get_db), patient: User = Depends(patient_only)):
    """Soft cancel: the row stays (status = cancelled) so history is kept."""
    try:
        appointment = svc.cancel_appointment(db, patient, appointment_id)
    except (svc.AppointmentNotFound, svc.NotChangeable, svc.TooLateToChange) as exc:
        raise _http_error(exc)
    return svc.to_out(db, appointment)


@router.get("/me/appointments", response_model=AppointmentPage)
def my_appointments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: AppointmentStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    patient: User = Depends(patient_only),
):
    return svc.list_my_appointments(
        db, patient, page, page_size, status_filter.value if status_filter else None
    )
