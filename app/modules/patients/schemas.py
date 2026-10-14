from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNKNOWN = "unknown"


def validate_dob(v: date) -> date:
    if v > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    if v.year < 1900:
        raise ValueError("date_of_birth is implausibly old")
    return v


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date
    sex: Sex = Sex.UNKNOWN
    medical_record_number: str | None = Field(default=None, min_length=1, max_length=64)

    _dob = field_validator("date_of_birth")(validate_dob)


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    date_of_birth: date
    sex: Sex
    medical_record_number: str | None = None
    has_account: bool = False
