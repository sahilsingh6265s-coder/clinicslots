from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import Role, User
from app.schemas.doctor import DoctorCreate, DoctorOut
from app.services import doctor_service
from app.services.auth_service import EmailAlreadyRegistered

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
def admin_ping(user: User = Depends(require_roles(Role.admin.value))):
    """Admin-only test endpoint that proves role-based access works."""
    return {"message": f"hello admin {user.name}"}


@router.post("/doctors", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(
    data: DoctorCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(Role.admin.value)),
):
    try:
        return doctor_service.create_doctor(db, data)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
