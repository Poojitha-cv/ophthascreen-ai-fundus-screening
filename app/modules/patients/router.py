from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import get_current_user, get_db, require_doctor
from app.core.pagination import Page, PageParams
from app.modules.auth.models import User
from app.modules.patients import service
from app.modules.patients.schemas import PatientCreate, PatientOut

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/me", response_model=PatientOut)
def my_patient_record(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.to_out(service.get_own_patient(db, user))


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCreate, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    """Doctor enrols a patient who has no account (e.g. walk-in)."""
    try:
        p = service.create_patient(db, full_name=body.full_name, date_of_birth=body.date_of_birth, sex=body.sex,
                                   medical_record_number=body.medical_record_number, user_id=None, created_by=doctor.id)
        audit(db, request, doctor.id, "patient.create", "patient", p.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "medical_record_number already exists")
    return service.to_out(p)


@router.get("", response_model=Page[PatientOut])
def list_patients(q: str | None = None, pg: PageParams = Depends(), doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    rows, total = service.search_patients(db, q, pg.offset, pg.size)
    return Page(items=[service.to_out(p) for p in rows], total=total, page=pg.page, size=pg.size)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = service.get_accessible_patient(db, user, patient_id)
    audit(db, request, user.id, "patient.view", "patient", p.id)
    db.commit()
    return service.to_out(p)
