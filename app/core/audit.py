"""Append-only audit trail for access to / changes of patient data."""
from __future__ import annotations

from datetime import datetime

from fastapi import Request
from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base, UTCDateTime, new_id, utcnow


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)


def audit(db: Session, request: Request | None, user_id: str | None, action: str,
          entity_type: str | None = None, entity_id: str | None = None, detail: dict | None = None) -> None:
    """Adds an audit row to the session; the caller commits (so it is atomic with the action)."""
    ip = request.client.host if request is not None and request.client else None
    db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, ip=ip, detail=detail))
