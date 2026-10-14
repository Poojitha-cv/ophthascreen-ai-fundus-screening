# # """ORM -> API schemas, applying role-based visibility in ONE place."""
# # from __future__ import annotations

# # from app.core.config import Settings
# # from app.modules.auth.models import Role, User
# # from app.modules.inference.protocol import RESEARCH_NOTICE
# # from app.modules.reviews.models import DoctorReview
# # from app.modules.screenings.models import FundusImage, Prediction, Screening
# # from app.modules.screenings.schemas import (DiseaseScore, ImageOut, PredictionOut, QualityIssueOut, QualityOut,
# #                                             ReviewOut, RiskThresholds, ScreeningOut)


# # def review_out(r: DoctorReview) -> ReviewOut:
# #     return ReviewOut(id=r.id, prediction_id=r.prediction_id, doctor_id=r.doctor_id,
# #                      doctor_name=r.doctor.full_name if r.doctor else None, decision=r.decision.value,
# #                      impression=r.impression.value if r.impression else None, comment=r.comment, created_at=r.created_at)


# # def prediction_out(p: Prediction, disease_names: dict[str, str] | None = None) -> PredictionOut:
# #     meta = p.model_meta
# #     core = set(meta.get("core_classes", []))
# #     per_class = meta.get("disease_thr_per_class", {})
# #     glob = meta.get("disease_thr_global")
# #     flagged = set(p.flagged_diseases)
# #     names = disease_names or {}
# #     diseases = [DiseaseScore(code=c, name=names.get(c), probability=round(pr, 5), flagged=c in flagged, validated=c in core,
# #                              threshold=per_class.get(c, glob) if c in core else None)
# #                 for c, pr in sorted(p.disease_probs.items(), key=lambda kv: kv[1], reverse=True)]
# #     return PredictionOut(
# #         id=p.id, created_at=p.created_at, model_tag=p.model_tag, model_weights_sha256=p.model_weights_sha256,
# #         risk_probability=round(p.risk_prob, 5), risk_abnormal_screening=p.risk_abnormal_screening,
# #         risk_abnormal_max_f1=p.risk_abnormal_maxf1,
# #         risk_thresholds=RiskThresholds(screening=meta["risk_thr_sens95"], max_f1=meta["risk_thr_maxF1"]),
# #         risk_confidence=round(p.risk_confidence, 4), needs_review=p.needs_review, flagged_diseases=list(p.flagged_diseases),
# #         diseases=diseases, crop_ok=p.crop_ok, warnings=list(p.warnings), notice=RESEARCH_NOTICE)


# # def image_out(img: FundusImage, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None) -> ImageOut:
# #     is_doctor = viewer.role == Role.DOCTOR
# #     q = img.quality_report
# #     quality = QualityOut(status=img.quality_status, checker_version=q["checker_version"],
# #                          issues=[QualityIssueOut(**i) for i in q["issues"]], metrics=q["metrics"] if is_doctor else None)
# #     latest = img.predictions[0] if img.predictions else None
# #     review_status = None if latest is None else ("reviewed" if latest.reviews else "pending")
# #     show_ai = latest is not None and (is_doctor or settings.patient_can_see_ai_results)
# #     return ImageOut(
# #         id=img.id, screening_id=img.screening_id, eye=img.eye, is_current=img.is_current, uploaded_at=img.uploaded_at,
# #         original_filename=img.original_filename, width=img.width, height=img.height, size_bytes=img.size_bytes, sha256=img.sha256,
# #         quality=quality, analysis_status=img.analysis_status,
# #         prediction=prediction_out(latest, disease_names) if show_ai else None,
# #         review_status=review_status,
# #         reviews=[review_out(r) for r in latest.reviews] if (is_doctor and latest) else [],
# #         file_url=f"/api/v1/images/{img.id}/file")


# # def screening_out(s: Screening, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None,
# #                   include_superseded: bool = False) -> ScreeningOut:
# #     imgs = [i for i in s.images if include_superseded or i.is_current]
# #     return ScreeningOut(id=s.id, patient_id=s.patient_id, created_at=s.created_at,
# #                         images=[image_out(i, viewer, settings, disease_names) for i in imgs])
# """ORM -> API schemas, applying role-based visibility in ONE place."""
# from __future__ import annotations

# from app.core.config import Settings
# from app.modules.auth.models import Role, User
# from app.modules.inference.protocol import RESEARCH_NOTICE
# from app.modules.inference.rfmid_labels import BELOW_MESSAGE, NO_FLAG_MESSAGE, REVIEW_MESSAGE, RFMID_NAMES
# from app.modules.reviews.models import DoctorReview
# from app.modules.screenings.models import FundusImage, Prediction, Screening
# from app.modules.screenings.schemas import (DiseaseScore, ImageOut, PredictionOut, QualityIssueOut, QualityOut,
#                                             ReviewOut, RiskThresholds, ScreeningOut)

# TOP_N = 3  # abnormalities listed for a flagged image


# def review_out(r: DoctorReview) -> ReviewOut:
#     return ReviewOut(id=r.id, prediction_id=r.prediction_id, doctor_id=r.doctor_id,
#                      doctor_name=r.doctor.full_name if r.doctor else None, decision=r.decision.value,
#                      impression=r.impression.value if r.impression else None, comment=r.comment, created_at=r.created_at)


# def prediction_out(p: Prediction, disease_names: dict[str, str] | None = None) -> PredictionOut:
#     meta = p.model_meta
#     core = set(meta.get("core_classes", []))
#     per_class = meta.get("disease_thr_per_class", {})
#     glob = meta.get("disease_thr_global")
#     flagged = set(p.flagged_diseases)
#     names = {**RFMID_NAMES, **(disease_names or {})}
#     # Disease_Risk is NOT an abnormality: disease_probs holds only the 45 RFMiD abnormality columns.
#     diseases = [DiseaseScore(code=c, name=names.get(c), probability=round(pr, 5), flagged=c in flagged, validated=c in core,
#                              threshold=per_class.get(c, glob) if c in core else None)
#                 for c, pr in sorted(p.disease_probs.items(), key=lambda kv: kv[1], reverse=True)]
#     # Screening decision comes from the stored Disease_Risk flag (threshold recorded in model_meta); unchanged.
#     review = bool(p.risk_abnormal_screening)
#     top = [d for d in diseases if d.validated][:TOP_N] if review else []
#     return PredictionOut(
#         id=p.id, created_at=p.created_at, model_tag=p.model_tag, model_weights_sha256=p.model_weights_sha256,
#         risk_probability=round(p.risk_prob, 5), risk_abnormal_screening=p.risk_abnormal_screening,
#         risk_abnormal_max_f1=p.risk_abnormal_maxf1,
#         risk_thresholds=RiskThresholds(screening=meta["risk_thr_sens95"], max_f1=meta["risk_thr_maxF1"]),
#         risk_confidence=round(p.risk_confidence, 4), needs_review=p.needs_review,
#         screening_outcome="doctor_review_recommended" if review else "below_screening_threshold",
#         screening_message=REVIEW_MESSAGE if review else NO_FLAG_MESSAGE,
#         flagged_diseases=list(p.flagged_diseases), top_abnormalities=top, diseases=diseases, crop_ok=p.crop_ok, warnings=list(p.warnings), notice=RESEARCH_NOTICE)


# def image_out(img: FundusImage, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None) -> ImageOut:
#     is_doctor = viewer.role == Role.DOCTOR
#     q = img.quality_report
#     quality = QualityOut(status=img.quality_status, checker_version=q["checker_version"],
#                          issues=[QualityIssueOut(**i) for i in q["issues"]], metrics=q["metrics"] if is_doctor else None)
#     latest = img.predictions[0] if img.predictions else None
#     review_status = None if latest is None else ("reviewed" if latest.reviews else "pending")
#     show_ai = latest is not None and (is_doctor or settings.patient_can_see_ai_results)
#     return ImageOut(
#         id=img.id, screening_id=img.screening_id, eye=img.eye, is_current=img.is_current, uploaded_at=img.uploaded_at,
#         original_filename=img.original_filename, width=img.width, height=img.height, size_bytes=img.size_bytes, sha256=img.sha256,
#         quality=quality, analysis_status=img.analysis_status,
#         prediction=prediction_out(latest, disease_names) if show_ai else None,
#         review_status=review_status,
#         reviews=[review_out(r) for r in latest.reviews] if (is_doctor and latest) else [],
#         file_url=f"/api/v1/images/{img.id}/file")


# def screening_out(s: Screening, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None,
#                   include_superseded: bool = False) -> ScreeningOut:
#     imgs = [i for i in s.images if include_superseded or i.is_current]
#     return ScreeningOut(id=s.id, patient_id=s.patient_id, created_at=s.created_at,
#                         images=[image_out(i, viewer, settings, disease_names) for i in imgs])


#new version with clinical data
"""ORM -> API schemas, applying role-based visibility in ONE place."""
from __future__ import annotations

from app.core.config import Settings
from app.modules.auth.models import Role, User
from app.modules.inference.protocol import RESEARCH_NOTICE
from app.modules.inference.rfmid_labels import BELOW_MESSAGE, NO_FLAG_MESSAGE, REVIEW_MESSAGE, RFMID_NAMES
from app.modules.reviews.models import DoctorReview
from app.modules.risk.serializers import clinical_out, risk_out
from app.modules.screenings.models import FundusImage, Prediction, Screening
from app.modules.screenings.schemas import (DiseaseScore, ImageOut, PredictionOut, QualityIssueOut, QualityOut,
                                            ReviewOut, RiskThresholds, ScreeningOut)

TOP_N = 3  # abnormalities listed for a flagged image


def review_out(r: DoctorReview) -> ReviewOut:
    return ReviewOut(id=r.id, prediction_id=r.prediction_id, doctor_id=r.doctor_id,
                     doctor_name=r.doctor.full_name if r.doctor else None, decision=r.decision.value,
                     impression=r.impression.value if r.impression else None, comment=r.comment, created_at=r.created_at)


def prediction_out(p: Prediction, disease_names: dict[str, str] | None = None) -> PredictionOut:
    meta = p.model_meta
    core = set(meta.get("core_classes", []))
    per_class = meta.get("disease_thr_per_class", {})
    glob = meta.get("disease_thr_global")
    flagged = set(p.flagged_diseases)
    names = {**RFMID_NAMES, **(disease_names or {})}
    # Disease_Risk is NOT an abnormality: disease_probs holds only the 45 RFMiD abnormality columns.
    diseases = [DiseaseScore(code=c, name=names.get(c), probability=round(pr, 5), flagged=c in flagged, validated=c in core,
                             threshold=per_class.get(c, glob) if c in core else None)
                for c, pr in sorted(p.disease_probs.items(), key=lambda kv: kv[1], reverse=True)]
    # Screening decision comes from the stored Disease_Risk flag (threshold recorded in model_meta); unchanged.
    review = bool(p.risk_abnormal_screening)
    top = [d for d in diseases if d.validated][:TOP_N] if review else []
    return PredictionOut(
        id=p.id, created_at=p.created_at, model_tag=p.model_tag, model_weights_sha256=p.model_weights_sha256,
        risk_probability=round(p.risk_prob, 5), risk_abnormal_screening=p.risk_abnormal_screening,
        risk_abnormal_max_f1=p.risk_abnormal_maxf1,
        risk_thresholds=RiskThresholds(screening=meta["risk_thr_sens95"], max_f1=meta["risk_thr_maxF1"]),
        risk_confidence=round(p.risk_confidence, 4), needs_review=p.needs_review,
        screening_outcome="doctor_review_recommended" if review else "below_screening_threshold",
        screening_message=REVIEW_MESSAGE if review else NO_FLAG_MESSAGE,
        flagged_diseases=list(p.flagged_diseases), top_abnormalities=top, diseases=diseases, crop_ok=p.crop_ok, warnings=list(p.warnings), notice=RESEARCH_NOTICE)


def image_out(img: FundusImage, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None) -> ImageOut:
    is_doctor = viewer.role == Role.DOCTOR
    q = img.quality_report
    quality = QualityOut(status=img.quality_status, checker_version=q["checker_version"],
                         issues=[QualityIssueOut(**i) for i in q["issues"]], metrics=q["metrics"] if is_doctor else None)
    latest = img.predictions[0] if img.predictions else None
    review_status = None if latest is None else ("reviewed" if latest.reviews else "pending")
    show_ai = latest is not None and (is_doctor or settings.patient_can_see_ai_results)
    return ImageOut(
        id=img.id, screening_id=img.screening_id, eye=img.eye, is_current=img.is_current, uploaded_at=img.uploaded_at,
        original_filename=img.original_filename, width=img.width, height=img.height, size_bytes=img.size_bytes, sha256=img.sha256,
        quality=quality, analysis_status=img.analysis_status,
        prediction=prediction_out(latest, disease_names) if show_ai else None,
        review_status=review_status,
        reviews=[review_out(r) for r in latest.reviews] if (is_doctor and latest) else [],
        file_url=f"/api/v1/images/{img.id}/file")


def screening_out(s: Screening, viewer: User, settings: Settings, disease_names: dict[str, str] | None = None,
                  include_superseded: bool = False, extras: dict | None = None) -> ScreeningOut:
    """extras: {screening_id: (ClinicalRecord | None, ScreeningRisk | None)} from risk.service.extras_for()."""
    imgs = [i for i in s.images if include_superseded or i.is_current]
    rec, risk = (extras or {}).get(s.id, (None, None))
    return ScreeningOut(id=s.id, patient_id=s.patient_id, created_at=s.created_at,
                        images=[image_out(i, viewer, settings, disease_names) for i in imgs],
                        clinical=clinical_out(rec), risk=risk_out(risk, viewer, settings))
