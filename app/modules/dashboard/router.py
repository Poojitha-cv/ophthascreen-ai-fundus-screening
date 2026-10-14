from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_doctor
from app.core.pagination import Page, PageParams
from app.modules.auth.models import User
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardSummary, QueueItem, QueueSort, QueueStatus
from app.modules.screenings.models import Eye, QualityStatus

router = APIRouter(prefix="/dashboard", tags=["doctor dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return service.summary(db)


@router.get("/queue", response_model=Page[QueueItem])
def review_queue(status: QueueStatus = QueueStatus.PENDING_REVIEW, eye: Eye | None = None, quality: QualityStatus | None = None,
                 needs_review: bool | None = None, abnormal: bool | None = None, q: str | None = None, patient_id: str | None = None,
                 date_from: date | None = None, date_to: date | None = None, sort: QueueSort = QueueSort.PRIORITY,
                 pg: PageParams = Depends(), doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    """One row per current image. `abnormal` filters on the model's screening (high-sensitivity) threshold.
    Open a row via GET /images/{image_id}; record a review via POST /predictions/{prediction_id}/reviews.
    An image whose newest analysis has no review (e.g. after re-analysis) returns to pending_review."""
    f = service.QueueFilters(status=status, eye=eye, quality=quality, needs_review=needs_review, abnormal=abnormal, q=q,
                             patient_id=patient_id, date_from=date_from, date_to=date_to, sort=sort)
    items, total = service.queue(db, f, pg.offset, pg.size)
    return Page(items=items, total=total, page=pg.page, size=pg.size)
