"""Clinical record (one per screening) and stored risk results (append-only, newest = current).

Clinical data attaches to the Screening (one visit), exactly as docs/EXTENDING.md prescribes. Every field is nullable:
NULL means 'not recorded' and is never imputed. VA / IOP / CDR are per eye (OD = right, OS = left).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, new_id, utcnow


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    screening_id: Mapped[str] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), unique=True)   # one per visit
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    # systemic
    diabetes: Mapped[bool | None] = mapped_column(Boolean)
    diabetes_duration_years: Mapped[int | None] = mapped_column(Integer)
    hypertension: Mapped[bool | None] = mapped_column(Boolean)
    # symptoms
    blurred_vision: Mapped[bool | None] = mapped_column(Boolean)
    floaters: Mapped[bool | None] = mapped_column(Boolean)
    visual_field_loss: Mapped[bool | None] = mapped_column(Boolean)
    eye_pain: Mapped[bool | None] = mapped_column(Boolean)
    visual_distortion: Mapped[bool | None] = mapped_column(Boolean)
    # family / eye history
    family_history_glaucoma: Mapped[bool | None] = mapped_column(Boolean)
    family_history_diabetic_retinopathy: Mapped[bool | None] = mapped_column(Boolean)
    family_history_amd: Mapped[bool | None] = mapped_column(Boolean)
    previous_eye_condition: Mapped[str | None] = mapped_column(String(32))
    previous_eye_surgery: Mapped[bool | None] = mapped_column(Boolean)
    # measurements (doctor-entered): decimal visual acuity, intra-ocular pressure (mmHg), cup-to-disc ratio
    va_od: Mapped[float | None] = mapped_column(Float)
    va_os: Mapped[float | None] = mapped_column(Float)
    iop_od: Mapped[float | None] = mapped_column(Float)
    iop_os: Mapped[float | None] = mapped_column(Float)
    cdr_od: Mapped[float | None] = mapped_column(Float)
    cdr_os: Mapped[float | None] = mapped_column(Float)


class ScreeningRisk(Base):
    """One computed risk assessment. A new row is appended whenever the inputs change; the newest (is_current) row is
    the current result and older rows stay as history. `inputs` is the exact snapshot the pure function received and
    `result` is its full output (tiers, per-eye bands, drivers, decision path, data gaps, warnings), so a stored result
    can be re-explained later even if the rules file or the model changes. The ConvNeXt model itself is untouched."""
    __tablename__ = "screening_risks"
    __table_args__ = (Index("ix_screening_risks_current", "screening_id", "is_current"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    screening_id: Mapped[str] = mapped_column(ForeignKey("screenings.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    computed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    trigger: Mapped[str] = mapped_column(String(32))            # screening_created | image_added | reanalysis | clinical_updated | manual
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    rules_version: Mapped[str] = mapped_column(String(64))
    rules_sha256: Mapped[str] = mapped_column(String(64))
    tier: Mapped[str] = mapped_column(String(16), index=True)   # Low | Moderate | High | Incomplete
    clinical_status: Mapped[str] = mapped_column(String(16))    # complete | incomplete | not_provided
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
