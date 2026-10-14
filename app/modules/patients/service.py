from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.models import Role, User
from app.modules.patients.models import Patient
from app.modules.patients.schemas import PatientOut, Sex


def to_out(p: Patient) -> PatientOut:
    return PatientOut(id=p.id, full_name=p.full_name, date_of_birth=p.date_of_birth, sex=p.sex,
                      medical_record_number=p.medical_record_number, has_account=p.user_id is not None)


def create_patient(db: Session, *, full_name: str, date_of_birth: date, sex: Sex, medical_record_number: str | None,
                   user_id: str | None, created_by: str | None) -> Patient:
    p = Patient(full_name=full_name.strip(), date_of_birth=date_of_birth, sex=sex,
                medical_record_number=medical_record_number, user_id=user_id, created_by=created_by)
    db.add(p)
    db.flush()
    return p


def get_accessible_patient(db: Session, user: User, patient_id: str) -> Patient:
    """Doctors may access any patient; patients only their own. Others get 404 (no existence leak)."""
    p = db.get(Patient, patient_id)
    if p is None or (user.role == Role.PATIENT and p.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return p


def get_own_patient(db: Session, user: User) -> Patient:
    p = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No patient record linked to this account")
    return p


def search_patients(db: Session, q: str | None, offset: int, limit: int) -> tuple[list[Patient], int]:
    stmt = select(Patient)
    if q:
        esc = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(or_(Patient.full_name.ilike(f"%{esc}%", escape="\\"),
                              Patient.medical_record_number.ilike(f"{esc}%", escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Patient.full_name, Patient.id).offset(offset).limit(limit)).all()
    return list(rows), total
