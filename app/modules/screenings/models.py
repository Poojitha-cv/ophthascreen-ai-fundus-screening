"""Screening = one visit/encounter for a patient. It is the anchor that later modalities (clinical data,
fusion results) attach to via screening_id. Images and per-image AI predictions hang off it."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, new_id, utcnow


def _enum(e):
    return Enum(e, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x])


class Eye(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class QualityStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class AnalysisStatus(StrEnum):
    PENDING = "pending"                  # not analysed yet (model unavailable at upload time)
    COMPLETED = "completed"
    SKIPPED_QUALITY = "skipped_quality"  # quality check failed -> retake needed, model not run
    FAILED = "failed"                    # model raised an error


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    images: Mapped[list["FundusImage"]] = relationship(back_populates="screening", order_by="FundusImage.uploaded_at")


class FundusImage(Base):
    __tablename__ = "fundus_images"
    __table_args__ = (Index("ix_fundus_screening_eye", "screening_id", "eye"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    screening_id: Mapped[str] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    eye: Mapped[Eye] = mapped_column(_enum(Eye))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)  # False once a retake for the same eye replaces it

    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    quality_status: Mapped[QualityStatus] = mapped_column(_enum(QualityStatus), index=True)
    quality_report: Mapped[dict] = mapped_column(JSON)
    analysis_status: Mapped[AnalysisStatus] = mapped_column(_enum(AnalysisStatus), index=True)
    analysis_error: Mapped[str | None] = mapped_column(String(200))

    screening: Mapped[Screening] = relationship(back_populates="images")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="image", order_by="Prediction.created_at.desc(), Prediction.id.desc()")


class Prediction(Base):
    """One model run on one image. Re-running (new model version / retry) appends a row; history is kept."""
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    image_id: Mapped[str] = mapped_column(ForeignKey("fundus_images.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    model_tag: Mapped[str] = mapped_column(String(64))
    model_weights_sha256: Mapped[str] = mapped_column(String(64))
    model_meta: Mapped[dict] = mapped_column(JSON)  # thresholds/temperature/core classes in effect for this run

    risk_prob: Mapped[float] = mapped_column(Float, index=True)
    risk_abnormal_maxf1: Mapped[bool] = mapped_column(Boolean)
    risk_abnormal_screening: Mapped[bool] = mapped_column(Boolean, index=True)
    risk_confidence: Mapped[float] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, index=True)
    flagged_diseases: Mapped[list] = mapped_column(JSON)
    disease_probs: Mapped[dict] = mapped_column(JSON)
    crop_ok: Mapped[bool] = mapped_column(Boolean)
    warnings: Mapped[list] = mapped_column(JSON)
    inference_ms: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)  # float32[768], reserved for later fusion

    image: Mapped[FundusImage] = relationship(back_populates="predictions")
    reviews: Mapped[list["DoctorReview"]] = relationship(back_populates="prediction", order_by="DoctorReview.created_at.desc(), DoctorReview.id.desc()")
