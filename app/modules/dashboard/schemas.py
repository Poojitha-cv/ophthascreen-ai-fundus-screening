# from __future__ import annotations

# from datetime import date, datetime
# from enum import StrEnum

# from pydantic import BaseModel

# from app.modules.patients.schemas import Sex
# from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


# class QueueStatus(StrEnum):
#     PENDING_REVIEW = "pending_review"              # has an AI result, no doctor review yet (default)
#     REVIEWED = "reviewed"
#     QUALITY_FAILED = "quality_failed"              # retake needed; model was not run
#     ANALYSIS_INCOMPLETE = "analysis_incomplete"    # model unavailable / errored; can be re-run
#     ALL = "all"


# class QueueSort(StrEnum):
#     PRIORITY = "priority"   # AI-flagged abnormal first, then model-uncertain, then highest risk
#     NEWEST = "newest"
#     RISK = "risk"


# class QueuePatient(BaseModel):
#     id: str
#     full_name: str
#     medical_record_number: str | None
#     date_of_birth: date
#     sex: Sex


# class QueueReview(BaseModel):
#     decision: str
#     impression: str | None
#     doctor_name: str | None
#     created_at: datetime


# class CoreScore(BaseModel):
#     code: str
#     probability: float


# class QueueItem(BaseModel):
#     image_id: str
#     screening_id: str
#     prediction_id: str | None
#     patient: QueuePatient
#     eye: Eye
#     uploaded_at: datetime
#     quality_status: QualityStatus
#     quality_issue_codes: list[str]
#     analysis_status: AnalysisStatus
#     risk_probability: float | None
#     risk_abnormal_screening: bool | None
#     risk_abnormal_max_f1: bool | None
#     needs_review: bool | None
#     flagged_diseases: list[str]
#     top_core_diseases: list[CoreScore]   # top 3 of the validated ("core") classes only
#     review_status: str | None            # pending | reviewed | None (no AI result)
#     last_review: QueueReview | None


# class DashboardSummary(BaseModel):
#     generated_at: datetime
#     patients_total: int
#     screenings_total: int
#     current_images_total: int
#     pending_review: int
#     pending_flagged_abnormal: int        # pending AND at/above the screening threshold
#     pending_model_uncertain: int         # pending AND model says needs_review
#     reviewed_total: int
#     reviewed_today_utc: int
#     quality_failed: int
#     analysis_incomplete: int


from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.modules.patients.schemas import Sex
from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


class QueueStatus(StrEnum):
    PENDING_REVIEW = "pending_review"              # has an AI result, no doctor review yet (default)
    REVIEWED = "reviewed"
    QUALITY_FAILED = "quality_failed"              # retake needed; model was not run
    ANALYSIS_INCOMPLETE = "analysis_incomplete"    # model unavailable / errored; can be re-run
    ALL = "all"


class QueueSort(StrEnum):
    PRIORITY = "priority"   # AI-flagged abnormal first, then model-uncertain, then highest risk
    NEWEST = "newest"
    RISK = "risk"


class QueuePatient(BaseModel):
    id: str
    full_name: str
    medical_record_number: str | None
    date_of_birth: date
    sex: Sex


class QueueReview(BaseModel):
    decision: str
    impression: str | None
    doctor_name: str | None
    created_at: datetime


class CoreScore(BaseModel):
    code: str
    name: str | None = None
    probability: float


class QueueItem(BaseModel):
    image_id: str
    screening_id: str
    prediction_id: str | None
    patient: QueuePatient
    eye: Eye
    uploaded_at: datetime
    quality_status: QualityStatus
    quality_issue_codes: list[str]
    analysis_status: AnalysisStatus
    risk_probability: float | None
    risk_abnormal_screening: bool | None
    risk_abnormal_max_f1: bool | None
    needs_review: bool | None
    flagged_diseases: list[str]
    flagged_disease_names: dict[str, str] = {}   # code -> full RFMiD name, for the flagged codes
    top_core_diseases: list[CoreScore]   # top 3 of the validated ("core") classes only
    review_status: str | None            # pending | reviewed | None (no AI result)
    last_review: QueueReview | None


class DashboardSummary(BaseModel):
    generated_at: datetime
    patients_total: int
    screenings_total: int
    current_images_total: int
    pending_review: int
    pending_flagged_abnormal: int        # pending AND at/above the screening threshold
    pending_model_uncertain: int         # pending AND model says needs_review
    reviewed_total: int
    reviewed_today_utc: int
    quality_failed: int
    analysis_incomplete: int
