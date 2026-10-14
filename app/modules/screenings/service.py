# # """Upload -> quality check -> inference -> persist. Orchestration lives here; routers stay thin."""
# # from __future__ import annotations

# # import hashlib
# # import logging
# # from dataclasses import dataclass

# # import numpy as np
# # from fastapi import HTTPException, Request, UploadFile, status
# # from sqlalchemy import func, select, update
# # from sqlalchemy.orm import Session, selectinload

# # from app.core.audit import audit
# # from app.core.config import Settings
# # from app.core.database import new_id
# # from app.modules.auth.models import Role, User
# # from app.modules.imaging.quality import assess_quality, finalize
# # from app.modules.imaging.storage import ImageStorage
# # from app.modules.imaging.validation import DecodedUpload, decode_upload
# # from app.modules.inference.protocol import ImageModel
# # from app.modules.patients.models import Patient
# # from app.modules.reviews.models import DoctorReview
# # from app.modules.screenings.models import (AnalysisStatus, Eye, FundusImage, Prediction, QualityStatus, Screening)

# # log = logging.getLogger(__name__)

# # _LABELS = {Eye.LEFT: "left_image", Eye.RIGHT: "right_image"}


# # @dataclass
# # class Ctx:
# #     db: Session
# #     settings: Settings
# #     storage: ImageStorage
# #     engine: ImageModel | None
# #     user: User
# #     request: Request | None = None


# # # ---------- loading with access control ----------

# # def _eager():
# #     return selectinload(Screening.images).selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)


# # def get_accessible_screening(db: Session, user: User, screening_id: str) -> Screening:
# #     s = db.scalar(select(Screening).where(Screening.id == screening_id).options(_eager()))
# #     if s is not None and user.role == Role.PATIENT:
# #         owner = db.scalar(select(Patient.user_id).where(Patient.id == s.patient_id))
# #         if owner != user.id:
# #             s = None
# #     if s is None:
# #         raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
# #     return s


# # def get_accessible_image(db: Session, user: User, image_id: str) -> FundusImage:
# #     img = db.scalar(select(FundusImage).where(FundusImage.id == image_id).options(
# #         selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)))
# #     if img is not None and user.role == Role.PATIENT:
# #         owner = db.scalar(select(Patient.user_id).join(Screening, Screening.patient_id == Patient.id).where(Screening.id == img.screening_id))
# #         if owner != user.id:
# #             img = None
# #     if img is None:
# #         raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
# #     return img


# # def list_screenings(db: Session, patient_id: str, offset: int, limit: int) -> tuple[list[Screening], int]:
# #     base = select(Screening).where(Screening.patient_id == patient_id)
# #     total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
# #     rows = db.scalars(base.order_by(Screening.created_at.desc(), Screening.id).offset(offset).limit(limit).options(_eager())).all()
# #     return list(rows), total


# # # ---------- ingest ----------

# # def _ingest(ctx: Ctx, screening: Screening, eye: Eye, dec: DecodedUpload) -> FundusImage:
# #     """Store one decoded upload and run the quality check. Does not commit."""
# #     image_id = new_id()
# #     sha = hashlib.sha256(dec.data).hexdigest()
# #     report = assess_quality(dec.image, ctx.settings.quality)

# #     prior_eyes = ctx.db.scalars(select(FundusImage.eye).join(Screening, Screening.id == FundusImage.screening_id)
# #                                 .where(Screening.patient_id == screening.patient_id, FundusImage.sha256 == sha)).all()
# #     if prior_eyes:
# #         if any(e != eye for e in prior_eyes):
# #             report["issues"].append({"code": "identical_file_used_for_other_eye", "severity": "warn",
# #                                      "message": "This exact file was already uploaded for the other eye of this patient. Check the left/right labels."})
# #         else:
# #             report["issues"].append({"code": "duplicate_upload", "severity": "warn",
# #                                      "message": "This exact file was already uploaded for this patient and eye."})
# #         finalize(report)

# #     # a new image for the same eye in the same screening is a retake: it supersedes the older one (kept as history)
# #     ctx.db.execute(update(FundusImage).where(FundusImage.screening_id == screening.id, FundusImage.eye == eye,
# #                                              FundusImage.is_current.is_(True)).values(is_current=False))
# #     key = f"{screening.patient_id}/{screening.id}/{image_id}.{dec.extension}"
# #     ctx.storage.save(key, dec.data)
# #     img = FundusImage(id=image_id, screening_id=screening.id, eye=eye, is_current=True, storage_key=key,
# #                       original_filename=(dec.filename or None) and dec.filename[:255], content_type=dec.content_type,
# #                       size_bytes=len(dec.data), sha256=sha, width=dec.image.size[0], height=dec.image.size[1],
# #                       uploaded_by=ctx.user.id, quality_status=QualityStatus(report["status"]), quality_report=report,
# #                       analysis_status=AnalysisStatus.PENDING)
# #     ctx.db.add(img)
# #     ctx.db.flush()
# #     return img


# # def _analyze(ctx: Ctx, img: FundusImage) -> None:
# #     """Run the model on one image and store the prediction. Never raises: failures are recorded on the image."""
# #     if img.quality_status == QualityStatus.FAIL:
# #         img.analysis_status, img.analysis_error = AnalysisStatus.SKIPPED_QUALITY, None
# #         return
# #     if ctx.engine is None:
# #         img.analysis_status, img.analysis_error = AnalysisStatus.PENDING, "model_unavailable"
# #         return
# #     try:
# #         res = ctx.engine.predict_one(ctx.storage.path(img.storage_key))
# #     except Exception:
# #         log.exception("Inference failed for image %s", img.id)
# #         img.analysis_status, img.analysis_error = AnalysisStatus.FAILED, "inference_error"
# #         return
# #     info = ctx.engine.info
# #     pred = Prediction(
# #         image_id=img.id, model_tag=info.tag, model_weights_sha256=info.weights_sha256, model_meta=info.meta,
# #         risk_prob=res.risk_prob, risk_abnormal_maxf1=res.risk_abnormal_maxf1, risk_abnormal_screening=res.risk_abnormal_screening,
# #         risk_confidence=res.risk_confidence, needs_review=res.needs_review, flagged_diseases=res.flagged_diseases,
# #         disease_probs=res.disease_probs, crop_ok=res.crop_ok, warnings=res.warnings, inference_ms=res.inference_ms,
# #         embedding=np.asarray(res.embedding, dtype=np.float32).tobytes())
# #     ctx.db.add(pred)
# #     img.analysis_status, img.analysis_error = AnalysisStatus.COMPLETED, None
# #     ctx.db.flush()


# # def _decode_all(settings: Settings, uploads: dict[Eye, UploadFile]) -> dict[Eye, DecodedUpload]:
# #     return {eye: decode_upload(f, settings.max_upload_bytes, settings.max_image_pixels, _LABELS[eye]) for eye, f in uploads.items()}


# # def _cleanup(ctx: Ctx, keys: list[str]) -> None:
# #     for k in keys:
# #         try:
# #             ctx.storage.delete(k)
# #         except Exception:
# #             log.exception("Could not remove orphaned file %s", k)


# # def create_screening(ctx: Ctx, patient: Patient, uploads: dict[Eye, UploadFile]) -> Screening:
# #     uploads = {e: f for e, f in uploads.items() if f is not None}
# #     if not uploads:
# #         raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide left_image and/or right_image")
# #     decoded = _decode_all(ctx.settings, uploads)  # validate everything BEFORE writing anything

# #     # Phase 1: durably store screening + images + quality reports (no model involved).
# #     keys: list[str] = []
# #     try:
# #         screening = Screening(patient_id=patient.id, created_by=ctx.user.id)
# #         ctx.db.add(screening)
# #         ctx.db.flush()
# #         for eye in (Eye.LEFT, Eye.RIGHT):
# #             if eye in decoded:
# #                 keys.append(_ingest(ctx, screening, eye, decoded[eye]).storage_key)
# #         ctx.db.commit()
# #     except Exception:
# #         ctx.db.rollback()
# #         _cleanup(ctx, keys)
# #         raise

# #     # Phase 2: model inference. Images are already safe; a failure here leaves them 'pending'/'failed' and re-analysable.
# #     images = list(ctx.db.scalars(select(FundusImage).where(FundusImage.screening_id == screening.id).order_by(FundusImage.eye)))
# #     for img in images:
# #         _analyze(ctx, img)
# #     audit(ctx.db, ctx.request, ctx.user.id, "screening.create", "screening", screening.id,
# #           {"patient_id": patient.id, "images": [{"id": i.id, "eye": i.eye.value, "quality": i.quality_status.value,
# #                                                   "analysis": i.analysis_status.value} for i in images]})
# #     ctx.db.commit()
# #     return get_accessible_screening(ctx.db, ctx.user, screening.id)


# # def add_image(ctx: Ctx, screening: Screening, eye: Eye, upload: UploadFile) -> FundusImage:
# #     dec = decode_upload(upload, ctx.settings.max_upload_bytes, ctx.settings.max_image_pixels, "image")
# #     keys: list[str] = []
# #     try:
# #         img = _ingest(ctx, screening, eye, dec)
# #         keys.append(img.storage_key)
# #         ctx.db.commit()
# #     except Exception:
# #         ctx.db.rollback()
# #         _cleanup(ctx, keys)
# #         raise
# #     img = get_accessible_image(ctx.db, ctx.user, img.id)
# #     _analyze(ctx, img)
# #     audit(ctx.db, ctx.request, ctx.user.id, "image.upload", "image", img.id,
# #           {"screening_id": screening.id, "eye": eye.value, "quality": img.quality_status.value, "analysis": img.analysis_status.value})
# #     ctx.db.commit()
# #     return get_accessible_image(ctx.db, ctx.user, img.id)


# # def reanalyze(ctx: Ctx, img: FundusImage) -> FundusImage:
# #     """Doctor-triggered re-run (e.g. model was unavailable, or a new model version was installed)."""
# #     if img.quality_status == QualityStatus.FAIL:
# #         raise HTTPException(status.HTTP_409_CONFLICT, "Image failed the quality check; ask for a retake instead")
# #     if ctx.engine is None:
# #         raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not available")
# #     _analyze(ctx, img)
# #     audit(ctx.db, ctx.request, ctx.user.id, "image.reanalyze", "image", img.id, {"analysis": img.analysis_status.value})
# #     ctx.db.commit()
# #     return get_accessible_image(ctx.db, ctx.user, img.id)



# """Upload -> quality check -> inference -> persist. Orchestration lives here; routers stay thin."""
# from __future__ import annotations

# import hashlib
# import logging
# from dataclasses import dataclass

# import numpy as np
# from fastapi import HTTPException, Request, UploadFile, status
# from sqlalchemy import func, select, update
# from sqlalchemy.orm import Session, selectinload

# from app.core.audit import audit
# from app.core.config import Settings
# from app.core.database import new_id
# from app.modules.auth.models import Role, User
# from app.modules.imaging.quality import assess_quality, finalize
# from app.modules.imaging.storage import ImageStorage
# from app.modules.imaging.validation import DecodedUpload, decode_upload
# from app.modules.inference.protocol import RISK_TARGET, Explainer, GradCamResult, ImageModel
# from app.modules.patients.models import Patient
# from app.modules.reviews.models import DoctorReview
# from app.modules.screenings.models import (AnalysisStatus, Eye, FundusImage, Prediction, QualityStatus, Screening)

# log = logging.getLogger(__name__)

# _LABELS = {Eye.LEFT: "left_image", Eye.RIGHT: "right_image"}


# @dataclass
# class Ctx:
#     db: Session
#     settings: Settings
#     storage: ImageStorage
#     engine: ImageModel | None
#     user: User
#     request: Request | None = None


# # ---------- loading with access control ----------

# def _eager():
#     return selectinload(Screening.images).selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)


# def get_accessible_screening(db: Session, user: User, screening_id: str) -> Screening:
#     s = db.scalar(select(Screening).where(Screening.id == screening_id).options(_eager()))
#     if s is not None and user.role == Role.PATIENT:
#         owner = db.scalar(select(Patient.user_id).where(Patient.id == s.patient_id))
#         if owner != user.id:
#             s = None
#     if s is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
#     return s


# def get_accessible_image(db: Session, user: User, image_id: str) -> FundusImage:
#     img = db.scalar(select(FundusImage).where(FundusImage.id == image_id).options(
#         selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)))
#     if img is not None and user.role == Role.PATIENT:
#         owner = db.scalar(select(Patient.user_id).join(Screening, Screening.patient_id == Patient.id).where(Screening.id == img.screening_id))
#         if owner != user.id:
#             img = None
#     if img is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
#     return img


# def list_screenings(db: Session, patient_id: str, offset: int, limit: int) -> tuple[list[Screening], int]:
#     base = select(Screening).where(Screening.patient_id == patient_id)
#     total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
#     rows = db.scalars(base.order_by(Screening.created_at.desc(), Screening.id).offset(offset).limit(limit).options(_eager())).all()
#     return list(rows), total


# # ---------- ingest ----------

# def _ingest(ctx: Ctx, screening: Screening, eye: Eye, dec: DecodedUpload) -> FundusImage:
#     """Store one decoded upload and run the quality check. Does not commit."""
#     image_id = new_id()
#     sha = hashlib.sha256(dec.data).hexdigest()
#     report = assess_quality(dec.image, ctx.settings.quality)

#     prior_eyes = ctx.db.scalars(select(FundusImage.eye).join(Screening, Screening.id == FundusImage.screening_id)
#                                 .where(Screening.patient_id == screening.patient_id, FundusImage.sha256 == sha)).all()
#     if prior_eyes:
#         if any(e != eye for e in prior_eyes):
#             report["issues"].append({"code": "identical_file_used_for_other_eye", "severity": "warn",
#                                      "message": "This exact file was already uploaded for the other eye of this patient. Check the left/right labels."})
#         else:
#             report["issues"].append({"code": "duplicate_upload", "severity": "warn",
#                                      "message": "This exact file was already uploaded for this patient and eye."})
#         finalize(report)

#     # a new image for the same eye in the same screening is a retake: it supersedes the older one (kept as history)
#     ctx.db.execute(update(FundusImage).where(FundusImage.screening_id == screening.id, FundusImage.eye == eye,
#                                              FundusImage.is_current.is_(True)).values(is_current=False))
#     key = f"{screening.patient_id}/{screening.id}/{image_id}.{dec.extension}"
#     ctx.storage.save(key, dec.data)
#     img = FundusImage(id=image_id, screening_id=screening.id, eye=eye, is_current=True, storage_key=key,
#                       original_filename=(dec.filename or None) and dec.filename[:255], content_type=dec.content_type,
#                       size_bytes=len(dec.data), sha256=sha, width=dec.image.size[0], height=dec.image.size[1],
#                       uploaded_by=ctx.user.id, quality_status=QualityStatus(report["status"]), quality_report=report,
#                       analysis_status=AnalysisStatus.PENDING)
#     ctx.db.add(img)
#     ctx.db.flush()
#     return img


# def _analyze(ctx: Ctx, img: FundusImage) -> None:
#     """Run the model on one image and store the prediction. Never raises: failures are recorded on the image."""
#     if img.quality_status == QualityStatus.FAIL:
#         img.analysis_status, img.analysis_error = AnalysisStatus.SKIPPED_QUALITY, None
#         return
#     if ctx.engine is None:
#         img.analysis_status, img.analysis_error = AnalysisStatus.PENDING, "model_unavailable"
#         return
#     try:
#         res = ctx.engine.predict_one(ctx.storage.path(img.storage_key))
#     except Exception:
#         log.exception("Inference failed for image %s", img.id)
#         img.analysis_status, img.analysis_error = AnalysisStatus.FAILED, "inference_error"
#         return
#     info = ctx.engine.info
#     pred = Prediction(
#         image_id=img.id, model_tag=info.tag, model_weights_sha256=info.weights_sha256, model_meta=info.meta,
#         risk_prob=res.risk_prob, risk_abnormal_maxf1=res.risk_abnormal_maxf1, risk_abnormal_screening=res.risk_abnormal_screening,
#         risk_confidence=res.risk_confidence, needs_review=res.needs_review, flagged_diseases=res.flagged_diseases,
#         disease_probs=res.disease_probs, crop_ok=res.crop_ok, warnings=res.warnings, inference_ms=res.inference_ms,
#         embedding=np.asarray(res.embedding, dtype=np.float32).tobytes())
#     ctx.db.add(pred)
#     img.analysis_status, img.analysis_error = AnalysisStatus.COMPLETED, None
#     ctx.db.flush()


# def _decode_all(settings: Settings, uploads: dict[Eye, UploadFile]) -> dict[Eye, DecodedUpload]:
#     return {eye: decode_upload(f, settings.max_upload_bytes, settings.max_image_pixels, _LABELS[eye]) for eye, f in uploads.items()}


# def _cleanup(ctx: Ctx, keys: list[str]) -> None:
#     for k in keys:
#         try:
#             ctx.storage.delete(k)
#         except Exception:
#             log.exception("Could not remove orphaned file %s", k)


# def create_screening(ctx: Ctx, patient: Patient, uploads: dict[Eye, UploadFile]) -> Screening:
#     uploads = {e: f for e, f in uploads.items() if f is not None}
#     if not uploads:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide left_image and/or right_image")
#     decoded = _decode_all(ctx.settings, uploads)  # validate everything BEFORE writing anything

#     # Phase 1: durably store screening + images + quality reports (no model involved).
#     keys: list[str] = []
#     try:
#         screening = Screening(patient_id=patient.id, created_by=ctx.user.id)
#         ctx.db.add(screening)
#         ctx.db.flush()
#         for eye in (Eye.LEFT, Eye.RIGHT):
#             if eye in decoded:
#                 keys.append(_ingest(ctx, screening, eye, decoded[eye]).storage_key)
#         ctx.db.commit()
#     except Exception:
#         ctx.db.rollback()
#         _cleanup(ctx, keys)
#         raise

#     # Phase 2: model inference. Images are already safe; a failure here leaves them 'pending'/'failed' and re-analysable.
#     images = list(ctx.db.scalars(select(FundusImage).where(FundusImage.screening_id == screening.id).order_by(FundusImage.eye)))
#     for img in images:
#         _analyze(ctx, img)
#     audit(ctx.db, ctx.request, ctx.user.id, "screening.create", "screening", screening.id,
#           {"patient_id": patient.id, "images": [{"id": i.id, "eye": i.eye.value, "quality": i.quality_status.value,
#                                                   "analysis": i.analysis_status.value} for i in images]})
#     ctx.db.commit()
#     return get_accessible_screening(ctx.db, ctx.user, screening.id)


# def add_image(ctx: Ctx, screening: Screening, eye: Eye, upload: UploadFile) -> FundusImage:
#     dec = decode_upload(upload, ctx.settings.max_upload_bytes, ctx.settings.max_image_pixels, "image")
#     keys: list[str] = []
#     try:
#         img = _ingest(ctx, screening, eye, dec)
#         keys.append(img.storage_key)
#         ctx.db.commit()
#     except Exception:
#         ctx.db.rollback()
#         _cleanup(ctx, keys)
#         raise
#     img = get_accessible_image(ctx.db, ctx.user, img.id)
#     _analyze(ctx, img)
#     audit(ctx.db, ctx.request, ctx.user.id, "image.upload", "image", img.id,
#           {"screening_id": screening.id, "eye": eye.value, "quality": img.quality_status.value, "analysis": img.analysis_status.value})
#     ctx.db.commit()
#     return get_accessible_image(ctx.db, ctx.user, img.id)


# def reanalyze(ctx: Ctx, img: FundusImage) -> FundusImage:
#     """Doctor-triggered re-run (e.g. model was unavailable, or a new model version was installed)."""
#     if img.quality_status == QualityStatus.FAIL:
#         raise HTTPException(status.HTTP_409_CONFLICT, "Image failed the quality check; ask for a retake instead")
#     if ctx.engine is None:
#         raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not available")
#     _analyze(ctx, img)
#     audit(ctx.db, ctx.request, ctx.user.id, "image.reanalyze", "image", img.id, {"analysis": img.analysis_status.value})
#     ctx.db.commit()
#     return get_accessible_image(ctx.db, ctx.user, img.id)


# def gradcam(ctx: Ctx, img: FundusImage, target: str) -> tuple[Prediction, GradCamResult]:
#     """Attention map for the image's latest prediction. Doctor-only (enforced by the router).

#     Refuses when the map would not describe the stored prediction: no completed analysis, a failed crop step, or the loaded
#     weights differ from the ones that produced the prediction (re-run the analysis first)."""
#     if ctx.engine is None:
#         raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not available")
#     if not isinstance(ctx.engine, Explainer):
#         raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "The installed model does not support attention maps")
#     latest = img.predictions[0] if img.predictions else None
#     if latest is None or img.analysis_status != AnalysisStatus.COMPLETED:
#         raise HTTPException(status.HTTP_409_CONFLICT, "This image has no completed analysis")
#     if not latest.crop_ok:
#         raise HTTPException(status.HTTP_409_CONFLICT, "No fundus region was found in this image; an attention map would be meaningless")
#     if latest.model_weights_sha256 != ctx.engine.info.weights_sha256:
#         raise HTTPException(status.HTTP_409_CONFLICT, "This prediction was made with a different model version; re-run the analysis first")
#     allowed = [RISK_TARGET, *ctx.engine.info.core_classes]
#     if target not in allowed:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, f"target must be one of: {', '.join(allowed)} (only validated classes are offered)")
#     try:
#         res = ctx.engine.explain_one(ctx.storage.path(img.storage_key), target)
#     except Exception:
#         log.exception("Grad-CAM failed for image %s", img.id)
#         raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not generate the attention map")
#     audit(ctx.db, ctx.request, ctx.user.id, "image.gradcam", "image", img.id, {"prediction_id": latest.id, "target": target})
#     ctx.db.commit()
#     return latest, res

# new version with clinical data

"""Upload -> quality check -> inference -> persist. Orchestration lives here; routers stay thin."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import numpy as np
from fastapi import HTTPException, Request, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.config import Settings
from app.core.database import new_id
from app.modules.auth.models import Role, User
from app.modules.imaging.quality import assess_quality, finalize
from app.modules.imaging.storage import ImageStorage
from app.modules.imaging.validation import DecodedUpload, decode_upload
from app.modules.inference.protocol import RISK_TARGET, Explainer, GradCamResult, ImageModel
from app.modules.patients.models import Patient
from app.modules.reviews.models import DoctorReview
from app.modules.risk import service as risk_service
from app.modules.risk.schemas import ClinicalIn
from app.modules.screenings.models import (AnalysisStatus, Eye, FundusImage, Prediction, QualityStatus, Screening)

log = logging.getLogger(__name__)

_LABELS = {Eye.LEFT: "left_image", Eye.RIGHT: "right_image"}


@dataclass
class Ctx:
    db: Session
    settings: Settings
    storage: ImageStorage
    engine: ImageModel | None
    user: User
    request: Request | None = None


# ---------- loading with access control ----------

def _eager():
    return selectinload(Screening.images).selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)


def get_accessible_screening(db: Session, user: User, screening_id: str) -> Screening:
    s = db.scalar(select(Screening).where(Screening.id == screening_id).options(_eager()))
    if s is not None and user.role == Role.PATIENT:
        owner = db.scalar(select(Patient.user_id).where(Patient.id == s.patient_id))
        if owner != user.id:
            s = None
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
    return s


def get_accessible_image(db: Session, user: User, image_id: str) -> FundusImage:
    img = db.scalar(select(FundusImage).where(FundusImage.id == image_id).options(
        selectinload(FundusImage.predictions).selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)))
    if img is not None and user.role == Role.PATIENT:
        owner = db.scalar(select(Patient.user_id).join(Screening, Screening.patient_id == Patient.id).where(Screening.id == img.screening_id))
        if owner != user.id:
            img = None
    if img is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return img


def list_screenings(db: Session, patient_id: str, offset: int, limit: int) -> tuple[list[Screening], int]:
    base = select(Screening).where(Screening.patient_id == patient_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Screening.created_at.desc(), Screening.id).offset(offset).limit(limit).options(_eager())).all()
    return list(rows), total


# ---------- ingest ----------

def _ingest(ctx: Ctx, screening: Screening, eye: Eye, dec: DecodedUpload) -> FundusImage:
    """Store one decoded upload and run the quality check. Does not commit."""
    image_id = new_id()
    sha = hashlib.sha256(dec.data).hexdigest()
    report = assess_quality(dec.image, ctx.settings.quality)

    prior_eyes = ctx.db.scalars(select(FundusImage.eye).join(Screening, Screening.id == FundusImage.screening_id)
                                .where(Screening.patient_id == screening.patient_id, FundusImage.sha256 == sha)).all()
    if prior_eyes:
        if any(e != eye for e in prior_eyes):
            report["issues"].append({"code": "identical_file_used_for_other_eye", "severity": "warn",
                                     "message": "This exact file was already uploaded for the other eye of this patient. Check the left/right labels."})
        else:
            report["issues"].append({"code": "duplicate_upload", "severity": "warn",
                                     "message": "This exact file was already uploaded for this patient and eye."})
        finalize(report)

    # a new image for the same eye in the same screening is a retake: it supersedes the older one (kept as history)
    ctx.db.execute(update(FundusImage).where(FundusImage.screening_id == screening.id, FundusImage.eye == eye,
                                             FundusImage.is_current.is_(True)).values(is_current=False))
    key = f"{screening.patient_id}/{screening.id}/{image_id}.{dec.extension}"
    ctx.storage.save(key, dec.data)
    img = FundusImage(id=image_id, screening_id=screening.id, eye=eye, is_current=True, storage_key=key,
                      original_filename=(dec.filename or None) and dec.filename[:255], content_type=dec.content_type,
                      size_bytes=len(dec.data), sha256=sha, width=dec.image.size[0], height=dec.image.size[1],
                      uploaded_by=ctx.user.id, quality_status=QualityStatus(report["status"]), quality_report=report,
                      analysis_status=AnalysisStatus.PENDING)
    ctx.db.add(img)
    ctx.db.flush()
    return img


def _analyze(ctx: Ctx, img: FundusImage) -> None:
    """Run the model on one image and store the prediction. Never raises: failures are recorded on the image."""
    if img.quality_status == QualityStatus.FAIL:
        img.analysis_status, img.analysis_error = AnalysisStatus.SKIPPED_QUALITY, None
        return
    if ctx.engine is None:
        img.analysis_status, img.analysis_error = AnalysisStatus.PENDING, "model_unavailable"
        return
    try:
        res = ctx.engine.predict_one(ctx.storage.path(img.storage_key))
    except Exception:
        log.exception("Inference failed for image %s", img.id)
        img.analysis_status, img.analysis_error = AnalysisStatus.FAILED, "inference_error"
        return
    info = ctx.engine.info
    pred = Prediction(
        image_id=img.id, model_tag=info.tag, model_weights_sha256=info.weights_sha256, model_meta=info.meta,
        risk_prob=res.risk_prob, risk_abnormal_maxf1=res.risk_abnormal_maxf1, risk_abnormal_screening=res.risk_abnormal_screening,
        risk_confidence=res.risk_confidence, needs_review=res.needs_review, flagged_diseases=res.flagged_diseases,
        disease_probs=res.disease_probs, crop_ok=res.crop_ok, warnings=res.warnings, inference_ms=res.inference_ms,
        embedding=np.asarray(res.embedding, dtype=np.float32).tobytes())
    ctx.db.add(pred)
    img.analysis_status, img.analysis_error = AnalysisStatus.COMPLETED, None
    ctx.db.flush()


def _decode_all(settings: Settings, uploads: dict[Eye, UploadFile]) -> dict[Eye, DecodedUpload]:
    return {eye: decode_upload(f, settings.max_upload_bytes, settings.max_image_pixels, _LABELS[eye]) for eye, f in uploads.items()}


def _cleanup(ctx: Ctx, keys: list[str]) -> None:
    for k in keys:
        try:
            ctx.storage.delete(k)
        except Exception:
            log.exception("Could not remove orphaned file %s", k)


def create_screening(ctx: Ctx, patient: Patient, uploads: dict[Eye, UploadFile], clinical: ClinicalIn | None = None) -> Screening:
    uploads = {e: f for e, f in uploads.items() if f is not None}
    if not uploads:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide left_image and/or right_image")
    decoded = _decode_all(ctx.settings, uploads)  # validate everything BEFORE writing anything

    # Phase 1: durably store screening + images + quality reports (no model involved).
    keys: list[str] = []
    try:
        screening = Screening(patient_id=patient.id, created_by=ctx.user.id)
        ctx.db.add(screening)
        ctx.db.flush()
        for eye in (Eye.LEFT, Eye.RIGHT):
            if eye in decoded:
                keys.append(_ingest(ctx, screening, eye, decoded[eye]).storage_key)
        if clinical is not None:                       # same transaction as the screening: both stored or neither
            risk_service.save_clinical(ctx.db, screening, clinical, ctx.user, ctx.request)
        ctx.db.commit()
    except Exception:
        ctx.db.rollback()
        _cleanup(ctx, keys)
        raise

    # Phase 2: model inference. Images are already safe; a failure here leaves them 'pending'/'failed' and re-analysable.
    images = list(ctx.db.scalars(select(FundusImage).where(FundusImage.screening_id == screening.id).order_by(FundusImage.eye)))
    for img in images:
        _analyze(ctx, img)
    risk_service.refresh_risk(ctx.db, screening.id, ctx.user.id, "screening_created")   # image output + clinical -> Low/Moderate/High
    audit(ctx.db, ctx.request, ctx.user.id, "screening.create", "screening", screening.id,
          {"patient_id": patient.id, "images": [{"id": i.id, "eye": i.eye.value, "quality": i.quality_status.value,
                                                  "analysis": i.analysis_status.value} for i in images]})
    ctx.db.commit()
    return get_accessible_screening(ctx.db, ctx.user, screening.id)


def add_image(ctx: Ctx, screening: Screening, eye: Eye, upload: UploadFile) -> FundusImage:
    dec = decode_upload(upload, ctx.settings.max_upload_bytes, ctx.settings.max_image_pixels, "image")
    keys: list[str] = []
    try:
        img = _ingest(ctx, screening, eye, dec)
        keys.append(img.storage_key)
        ctx.db.commit()
    except Exception:
        ctx.db.rollback()
        _cleanup(ctx, keys)
        raise
    img = get_accessible_image(ctx.db, ctx.user, img.id)
    _analyze(ctx, img)
    risk_service.refresh_risk(ctx.db, screening.id, ctx.user.id, "image_added")
    audit(ctx.db, ctx.request, ctx.user.id, "image.upload", "image", img.id,
          {"screening_id": screening.id, "eye": eye.value, "quality": img.quality_status.value, "analysis": img.analysis_status.value})
    ctx.db.commit()
    return get_accessible_image(ctx.db, ctx.user, img.id)


def reanalyze(ctx: Ctx, img: FundusImage) -> FundusImage:
    """Doctor-triggered re-run (e.g. model was unavailable, or a new model version was installed)."""
    if img.quality_status == QualityStatus.FAIL:
        raise HTTPException(status.HTTP_409_CONFLICT, "Image failed the quality check; ask for a retake instead")
    if ctx.engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not available")
    _analyze(ctx, img)
    risk_service.refresh_risk(ctx.db, img.screening_id, ctx.user.id, "reanalysis")
    audit(ctx.db, ctx.request, ctx.user.id, "image.reanalyze", "image", img.id, {"analysis": img.analysis_status.value})
    ctx.db.commit()
    return get_accessible_image(ctx.db, ctx.user, img.id)


def gradcam(ctx: Ctx, img: FundusImage, target: str) -> tuple[Prediction, GradCamResult]:
    """Attention map for the image's latest prediction. Doctor-only (enforced by the router).

    Refuses when the map would not describe the stored prediction: no completed analysis, a failed crop step, or the loaded
    weights differ from the ones that produced the prediction (re-run the analysis first)."""
    if ctx.engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Model is not available")
    if not isinstance(ctx.engine, Explainer):
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "The installed model does not support attention maps")
    latest = img.predictions[0] if img.predictions else None
    if latest is None or img.analysis_status != AnalysisStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This image has no completed analysis")
    if not latest.crop_ok:
        raise HTTPException(status.HTTP_409_CONFLICT, "No fundus region was found in this image; an attention map would be meaningless")
    if latest.model_weights_sha256 != ctx.engine.info.weights_sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "This prediction was made with a different model version; re-run the analysis first")
    allowed = [RISK_TARGET, *ctx.engine.info.core_classes]
    if target not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"target must be one of: {', '.join(allowed)} (only validated classes are offered)")
    try:
        res = ctx.engine.explain_one(ctx.storage.path(img.storage_key), target)
    except Exception:
        log.exception("Grad-CAM failed for image %s", img.id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not generate the attention map")
    audit(ctx.db, ctx.request, ctx.user.id, "image.gradcam", "image", img.id, {"prediction_id": latest.id, "target": target})
    ctx.db.commit()
    return latest, res

