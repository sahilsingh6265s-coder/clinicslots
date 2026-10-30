from datetime import date as date_type, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import Role, User
from app.schemas.doctor import DoctorCreate, DoctorOut
from app.schemas.stats import StatsOut
from app.services import doctor_service, stats_service
from app.services.auth_service import EmailAlreadyRegistered

router = APIRouter(prefix="/admin", tags=["admin"])

admin_only = require_roles(Role.admin.value)


@router.get("/ping")
def admin_ping(user: User = Depends(admin_only)):
    """Admin-only test endpoint that proves role-based access works."""
    return {"message": f"hello admin {user.name}"}


@router.post("/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(data: DoctorCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    try:
        return doctor_service.create_doctor(db, data)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


@router.delete("/doctors/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_doctor(doctor_id: int, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    """Deactivate a doctor. History is kept; refused while upcoming appointments exist."""
    try:
        doctor_service.remove_doctor(db, doctor_id)
    except doctor_service.DoctorNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    except doctor_service.DoctorHasUpcomingAppointments as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{exc}. Cancel or complete them first.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stats", response_model=StatsOut)
def stats(
    from_date: date_type | None = Query(None, description="Clinic-local date; default = 29 days before to_date"),
    to_date: date_type | None = Query(None, description="Clinic-local date; default = today"),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    tz = ZoneInfo(settings.clinic_timezone)
    to_date = to_date or datetime.now(tz).date()
    from_date = from_date or (to_date - timedelta(days=29))
    try:
        return stats_service.compute_stats(db, from_date, to_date, tz, settings.clinic_timezone)
    except stats_service.InvalidRange as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
