from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.auth.models import Role
from app.modules.patients.schemas import Sex, validate_dob


class RegisterRequest(BaseModel):
    """Patient self-registration. Doctor accounts can NOT be created here (use scripts/create_doctor.py)."""
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date
    sex: Sex = Sex.UNKNOWN

    _dob = field_validator("date_of_birth")(validate_dob)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Role
    user_id: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    patient_id: str | None = None
