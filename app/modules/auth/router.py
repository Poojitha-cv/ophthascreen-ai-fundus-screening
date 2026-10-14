from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import Settings
from app.core.database import utcnow
from app.core.deps import get_current_user, get_db, get_settings_dep
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth import service
from app.modules.auth.models import Role, User
from app.modules.auth.schemas import ChangePasswordRequest, RegisterRequest, TokenOut, UserOut
from app.modules.patients import service as patient_service
from app.modules.patients.models import Patient

router = APIRouter(prefix="/auth", tags=["auth"])

_BAD_LOGIN = "Incorrect email or password, or account temporarily locked"


def _user_out(db: Session, user: User) -> UserOut:
    pid = db.scalar(select(Patient.id).where(Patient.user_id == user.id)) if user.role == Role.PATIENT else None
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role, patient_id=pid)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_patient(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Self-registration creates a PATIENT account + linked patient record. Doctors cannot self-register."""
    if service.get_user_by_email(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    try:
        user = service.create_user(db, email=body.email, password=body.password, full_name=body.full_name, role=Role.PATIENT)
        patient_service.create_patient(db, full_name=body.full_name, date_of_birth=body.date_of_birth, sex=body.sex,
                                       medical_record_number=None, user_id=user.id, created_by=user.id)
        audit(db, request, user.id, "auth.register", "user", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return _user_out(db, user)


@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings_dep)):
    user, outcome = service.authenticate(db, form.username, form.password, settings)
    audit(db, request, user.id if user else None, "auth.login" if user else "auth.login_failed",
          "user", user.id if user else None, None if user else {"reason": outcome})
    db.commit()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_LOGIN, headers={"WWW-Authenticate": "Bearer"})
    token, expires_in = create_access_token(user.id, user.role.value, settings)
    return TokenOut(access_token=token, expires_in=expires_in, role=user.role, user_id=user.id)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_out(db, user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()  # invalidates all previously issued tokens
    audit(db, request, user.id, "auth.password_change", "user", user.id)
    db.commit()
