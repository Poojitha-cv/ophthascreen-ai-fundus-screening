# # # from __future__ import annotations

# # # from datetime import datetime
# # # from typing import Literal

# # # from pydantic import BaseModel

# # # from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


# # # class QualityIssueOut(BaseModel):
# # #     code: str
# # #     severity: Literal["warn", "fail"]
# # #     message: str


# # # class QualityOut(BaseModel):
# # #     status: QualityStatus
# # #     checker_version: str
# # #     issues: list[QualityIssueOut]
# # #     metrics: dict | None = None  # doctors only


# # # class DiseaseScore(BaseModel):
# # #     code: str
# # #     name: str | None = None            # only if models/<tag>/disease_names.json is provided
# # #     probability: float
# # #     flagged: bool
# # #     validated: bool                    # True only for the model's "core" classes; others are probabilities only
# # #     threshold: float | None = None     # decision threshold (core classes only)


# # # class RiskThresholds(BaseModel):
# # #     screening: float                   # sensitivity-oriented operating point (val sens >= 95%)
# # #     max_f1: float


# # # class PredictionOut(BaseModel):
# # #     id: str
# # #     created_at: datetime
# # #     model_tag: str
# # #     model_weights_sha256: str
# # #     risk_probability: float
# # #     risk_abnormal_screening: bool
# # #     risk_abnormal_max_f1: bool
# # #     risk_thresholds: RiskThresholds
# # #     risk_confidence: float
# # #     needs_review: bool
# # #     flagged_diseases: list[str]
# # #     diseases: list[DiseaseScore]
# # #     crop_ok: bool
# # #     warnings: list[str]
# # #     notice: str


# # # class ReviewOut(BaseModel):
# # #     id: str
# # #     prediction_id: str
# # #     doctor_id: str | None
# # #     doctor_name: str | None
# # #     decision: str
# # #     impression: str | None
# # #     comment: str | None
# # #     created_at: datetime


# # # class ImageOut(BaseModel):
# # #     id: str
# # #     screening_id: str
# # #     eye: Eye
# # #     is_current: bool
# # #     uploaded_at: datetime
# # #     original_filename: str | None
# # #     width: int
# # #     height: int
# # #     size_bytes: int
# # #     sha256: str
# # #     quality: QualityOut
# # #     analysis_status: AnalysisStatus
# # #     prediction: PredictionOut | None = None        # hidden from patients unless OPH_PATIENT_CAN_SEE_AI_RESULTS
# # #     review_status: Literal["pending", "reviewed"] | None = None   # None = nothing to review
# # #     reviews: list[ReviewOut] = []                   # doctors only
# # #     file_url: str


# # # class ScreeningOut(BaseModel):
# # #     id: str
# # #     patient_id: str
# # #     created_at: datetime
# # #     images: list[ImageOut]


# # from __future__ import annotations

# # from datetime import datetime
# # from typing import Literal

# # from pydantic import BaseModel

# # from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


# # class QualityIssueOut(BaseModel):
# #     code: str
# #     severity: Literal["warn", "fail"]
# #     message: str


# # class QualityOut(BaseModel):
# #     status: QualityStatus
# #     checker_version: str
# #     issues: list[QualityIssueOut]
# #     metrics: dict | None = None  # doctors only


# # class DiseaseScore(BaseModel):
# #     code: str
# #     name: str | None = None            # full RFMiD name (app/modules/inference/rfmid_labels.py)
# #     probability: float
# #     flagged: bool
# #     validated: bool                    # True only for the model's "core" classes; others are probabilities only
# #     threshold: float | None = None     # decision threshold (core classes only)


# # class RiskThresholds(BaseModel):
# #     screening: float                   # sensitivity-oriented operating point (val sens >= 95%)
# #     max_f1: float


# # class PredictionOut(BaseModel):
# #     id: str
# #     created_at: datetime
# #     model_tag: str
# #     model_weights_sha256: str
# #     risk_probability: float
# #     risk_abnormal_screening: bool
# #     risk_abnormal_max_f1: bool
# #     risk_thresholds: RiskThresholds
# #     risk_confidence: float
# #     needs_review: bool
# #     screening_outcome: Literal["below_screening_threshold", "doctor_review_recommended"]
# #     screening_message: str             # "No significant abnormality flagged" | "Doctor review recommended"
# #     flagged_diseases: list[str]
# #     top_abnormalities: list[DiseaseScore] = []   # only when review is recommended: highest-probability VALIDATED classes
# #     diseases: list[DiseaseScore]
# #     crop_ok: bool
# #     warnings: list[str]
# #     notice: str


# # class ReviewOut(BaseModel):
# #     id: str
# #     prediction_id: str
# #     doctor_id: str | None
# #     doctor_name: str | None
# #     decision: str
# #     impression: str | None
# #     comment: str | None
# #     created_at: datetime


# # class ImageOut(BaseModel):
# #     id: str
# #     screening_id: str
# #     eye: Eye
# #     is_current: bool
# #     uploaded_at: datetime
# #     original_filename: str | None
# #     width: int
# #     height: int
# #     size_bytes: int
# #     sha256: str
# #     quality: QualityOut
# #     analysis_status: AnalysisStatus
# #     prediction: PredictionOut | None = None        # hidden from patients unless OPH_PATIENT_CAN_SEE_AI_RESULTS
# #     review_status: Literal["pending", "reviewed"] | None = None   # None = nothing to review
# #     reviews: list[ReviewOut] = []                   # doctors only
# #     file_url: str


# # class ScreeningOut(BaseModel):
# #     id: str
# #     patient_id: str
# #     created_at: datetime
# #     images: list[ImageOut]


# from __future__ import annotations

# from datetime import datetime
# from typing import Literal

# from pydantic import BaseModel

# from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


# class QualityIssueOut(BaseModel):
#     code: str
#     severity: Literal["warn", "fail"]
#     message: str


# class QualityOut(BaseModel):
#     status: QualityStatus
#     checker_version: str
#     issues: list[QualityIssueOut]
#     metrics: dict | None = None  # doctors only


# class DiseaseScore(BaseModel):
#     code: str
#     name: str | None = None            # full RFMiD name (app/modules/inference/rfmid_labels.py)
#     probability: float
#     flagged: bool
#     validated: bool                    # True only for the model's "core" classes; others are probabilities only
#     threshold: float | None = None     # decision threshold (core classes only)


# class RiskThresholds(BaseModel):
#     screening: float                   # sensitivity-oriented operating point (val sens >= 95%)
#     max_f1: float


# class PredictionOut(BaseModel):
#     id: str
#     created_at: datetime
#     model_tag: str
#     model_weights_sha256: str
#     risk_probability: float
#     risk_abnormal_screening: bool
#     risk_abnormal_max_f1: bool
#     risk_thresholds: RiskThresholds
#     risk_confidence: float
#     needs_review: bool
#     screening_outcome: Literal["below_screening_threshold", "doctor_review_recommended"]
#     screening_message: str             # "No significant abnormality flagged" | "Doctor review recommended"
#     flagged_diseases: list[str]
#     top_abnormalities: list[DiseaseScore] = []   # only when review is recommended: highest-probability VALIDATED classes
#     diseases: list[DiseaseScore]
#     crop_ok: bool
#     warnings: list[str]
#     notice: str


# class ReviewOut(BaseModel):
#     id: str
#     prediction_id: str
#     doctor_id: str | None
#     doctor_name: str | None
#     decision: str
#     impression: str | None
#     comment: str | None
#     created_at: datetime


# class ImageOut(BaseModel):
#     id: str
#     screening_id: str
#     eye: Eye
#     is_current: bool
#     uploaded_at: datetime
#     original_filename: str | None
#     width: int
#     height: int
#     size_bytes: int
#     sha256: str
#     quality: QualityOut
#     analysis_status: AnalysisStatus
#     prediction: PredictionOut | None = None        # hidden from patients unless OPH_PATIENT_CAN_SEE_AI_RESULTS
#     review_status: Literal["pending", "reviewed"] | None = None   # None = nothing to review
#     reviews: list[ReviewOut] = []                   # doctors only
#     file_url: str


# class ScreeningOut(BaseModel):
#     id: str
#     patient_id: str
#     created_at: datetime
#     images: list[ImageOut]


# class GradCamOut(BaseModel):
#     image_id: str
#     prediction_id: str
#     target: str                        # "risk" or a validated RFMiD code
#     target_name: str
#     empty: bool                        # no positive contribution found -> do not show a map
#     overlay_jpeg_base64: str           # heat map blended onto the model's input view (cropped/squared fundus), NOT the raw upload
#     resolution: int
#     grid_size: int
#     model_tag: str
#     model_weights_sha256: str
#     notice: str


# new version with clinical data

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.modules.risk.schemas import ClinicalOut, RiskOut
from app.modules.screenings.models import AnalysisStatus, Eye, QualityStatus


class QualityIssueOut(BaseModel):
    code: str
    severity: Literal["warn", "fail"]
    message: str


class QualityOut(BaseModel):
    status: QualityStatus
    checker_version: str
    issues: list[QualityIssueOut]
    metrics: dict | None = None  # doctors only


class DiseaseScore(BaseModel):
    code: str
    name: str | None = None            # full RFMiD name (app/modules/inference/rfmid_labels.py)
    probability: float
    flagged: bool
    validated: bool                    # True only for the model's "core" classes; others are probabilities only
    threshold: float | None = None     # decision threshold (core classes only)


class RiskThresholds(BaseModel):
    screening: float                   # sensitivity-oriented operating point (val sens >= 95%)
    max_f1: float


class PredictionOut(BaseModel):
    id: str
    created_at: datetime
    model_tag: str
    model_weights_sha256: str
    risk_probability: float
    risk_abnormal_screening: bool
    risk_abnormal_max_f1: bool
    risk_thresholds: RiskThresholds
    risk_confidence: float
    needs_review: bool
    screening_outcome: Literal["below_screening_threshold", "doctor_review_recommended"]
    screening_message: str             # "No significant abnormality flagged" | "Doctor review recommended"
    flagged_diseases: list[str]
    top_abnormalities: list[DiseaseScore] = []   # only when review is recommended: highest-probability VALIDATED classes
    diseases: list[DiseaseScore]
    crop_ok: bool
    warnings: list[str]
    notice: str


class ReviewOut(BaseModel):
    id: str
    prediction_id: str
    doctor_id: str | None
    doctor_name: str | None
    decision: str
    impression: str | None
    comment: str | None
    created_at: datetime


class ImageOut(BaseModel):
    id: str
    screening_id: str
    eye: Eye
    is_current: bool
    uploaded_at: datetime
    original_filename: str | None
    width: int
    height: int
    size_bytes: int
    sha256: str
    quality: QualityOut
    analysis_status: AnalysisStatus
    prediction: PredictionOut | None = None        # hidden from patients unless OPH_PATIENT_CAN_SEE_AI_RESULTS
    review_status: Literal["pending", "reviewed"] | None = None   # None = nothing to review
    reviews: list[ReviewOut] = []                   # doctors only
    file_url: str


class ScreeningOut(BaseModel):
    id: str
    patient_id: str
    created_at: datetime
    images: list[ImageOut]
    clinical: ClinicalOut | None = None          # clinical record of this visit, if any
    risk: RiskOut | None = None                  # Low/Moderate/High assessment; hidden from patients unless OPH_PATIENT_CAN_SEE_AI_RESULTS


class GradCamOut(BaseModel):
    image_id: str
    prediction_id: str
    target: str                        # "risk" or a validated RFMiD code
    target_name: str
    empty: bool                        # no positive contribution found -> do not show a map
    overlay_jpeg_base64: str           # heat map blended onto the model's input view (cropped/squared fundus), NOT the raw upload
    resolution: int
    grid_size: int
    model_tag: str
    model_weights_sha256: str
    notice: str
