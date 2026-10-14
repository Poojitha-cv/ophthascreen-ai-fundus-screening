from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreviousEyeCondition(StrEnum):
    NONE = "none"
    CATARACT = "cataract"
    GLAUCOMA = "glaucoma"
    AMD = "amd"
    DIABETIC_RETINOPATHY = "diabetic_retinopathy"
    OTHER = "other"


MEASUREMENT_FIELDS = ("va_od", "va_os", "iop_od", "iop_os", "cdr_od", "cdr_os")   # doctor-entered only


class ClinicalIn(BaseModel):
    """Clinical inputs for one screening. Every field is optional; null / omitted = 'not recorded'.
    VA is decimal acuity, IOP is mmHg, CDR is the cup-to-disc ratio. OD = right eye, OS = left eye."""
    model_config = ConfigDict(extra="forbid")

    diabetes: bool | None = None
    diabetes_duration_years: int | None = Field(None, ge=0, le=80)
    hypertension: bool | None = None
    blurred_vision: bool | None = None
    floaters: bool | None = None
    visual_field_loss: bool | None = None
    eye_pain: bool | None = None
    visual_distortion: bool | None = None
    family_history_glaucoma: bool | None = None
    family_history_diabetic_retinopathy: bool | None = None
    family_history_amd: bool | None = None
    previous_eye_condition: PreviousEyeCondition | None = None
    previous_eye_surgery: bool | None = None
    va_od: float | None = Field(None, ge=0, le=2.0, allow_inf_nan=False)
    va_os: float | None = Field(None, ge=0, le=2.0, allow_inf_nan=False)
    iop_od: float | None = Field(None, ge=1, le=80, allow_inf_nan=False)
    iop_os: float | None = Field(None, ge=1, le=80, allow_inf_nan=False)
    cdr_od: float | None = Field(None, ge=0, le=1.0, allow_inf_nan=False)
    cdr_os: float | None = Field(None, ge=0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _duration_needs_diabetes(self):
        if self.diabetes is False and self.diabetes_duration_years:
            raise ValueError("diabetes_duration_years must be empty or 0 when diabetes is No")
        return self


CLINICAL_FIELDS = tuple(ClinicalIn.model_fields)


class ClinicalOut(ClinicalIn):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: str
    screening_id: str
    recorded_by: str | None = None
    schema_version: int
    created_at: datetime
    updated_at: datetime


# ---------- risk ----------

class NoteOut(BaseModel):
    code: str
    message: str
    eye: str | None = None
    field: str | None = None


class DriverOut(BaseModel):
    kind: str                      # image | clinical | red_flag | combination | override
    id: str
    label: str
    evidence: str                  # rfmid_validated | conventional_reference | heuristic
    effect: str
    scope: str = "eye"
    eye: str | None = None
    value: Any = None
    points: int | None = None


class DomainScoreOut(BaseModel):
    label: str
    score: int
    raw: int
    cap: int
    capped: bool


class EyeRiskOut(BaseModel):
    eye: str
    state: str                     # assessed | not_assessed
    not_assessed_reason: str | None = None
    image_band: str | None = None
    risk_prob: float | None = None
    thr_screening: float | None = None
    thr_max_f1: float | None = None
    needs_review: bool | None = None
    clinical_score: int
    clinical_max_score: int
    clinical_domain_scores: dict[str, DomainScoreOut]
    clinical_band: str
    red_flags: list[str] = []
    matrix_tier: str | None = None
    tier: str | None = None
    overrides_applied: list[str] = []
    drivers: list[DriverOut] = []


class RiskOut(BaseModel):
    id: str
    screening_id: str
    created_at: datetime
    trigger: str
    rules_version: str
    rules_sha256: str
    rules_status: str = ""
    tier: str                      # Low | Moderate | High | Incomplete
    tier_driven_by: str | None = None
    clinical_status: str
    eyes: dict[str, EyeRiskOut]
    patient_drivers: list[DriverOut] = []
    decision_path: list[str] = []
    data_gaps: list[NoteOut] = []
    warnings: list[NoteOut] = []
    evidence_legend: dict[str, str] = {}
    notice: str
    inputs: dict[str, Any] = {}    # exact snapshot the assessment was computed from


class ClinicalSaveOut(BaseModel):
    clinical: ClinicalOut
    risk: RiskOut | None = None    # None when the viewer may not see risk results (patients, by default) or it could not be computed
    changed_fields: list[str] = []
