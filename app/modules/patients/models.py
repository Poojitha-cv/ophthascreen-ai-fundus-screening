"""Patient identity/demographics only. Clinical data belongs in its own module and links via patient_id /
screening_id (see docs/EXTENDING.md)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, new_id, utcnow
from app.modules.patients.schemas import Sex


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Optional login. Patients enrolled by a doctor (no account) have user_id NULL.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    medical_record_number: Mapped[str | None] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(Enum(Sex, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]), default=Sex.UNKNOWN)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
