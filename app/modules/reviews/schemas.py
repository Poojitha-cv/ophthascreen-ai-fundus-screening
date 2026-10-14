from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.reviews.models import Decision, Impression


class ReviewCreate(BaseModel):
    decision: Decision
    impression: Impression | None = None
    comment: str | None = Field(default=None, max_length=2000)
