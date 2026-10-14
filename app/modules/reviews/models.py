from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, new_id, utcnow


class Decision(StrEnum):
    AGREE = "agree"                # doctor agrees with the AI result
    DISAGREE = "disagree"
    NEEDS_RETAKE = "needs_retake"  # image unusable / poor quality
    INCONCLUSIVE = "inconclusive"


class Impression(StrEnum):
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    UNGRADABLE = "ungradable"


class DoctorReview(Base):
    """Append-only: a correction is a new row; the newest row is the current review, older rows are history."""
    __tablename__ = "doctor_reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id", ondelete="RESTRICT"), index=True)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    decision: Mapped[Decision] = mapped_column(Enum(Decision, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x]))
    impression: Mapped[Impression | None] = mapped_column(Enum(Impression, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x]))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    prediction = relationship("Prediction", back_populates="reviews")
    doctor = relationship("User")
