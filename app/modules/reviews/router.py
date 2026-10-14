from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.deps import get_db, require_doctor
from app.modules.auth.models import User
from app.modules.reviews.models import DoctorReview
from app.modules.reviews.schemas import ReviewCreate
from app.modules.screenings.models import FundusImage, Prediction
from app.modules.screenings.schemas import ReviewOut
from app.modules.screenings.serializers import review_out

router = APIRouter(prefix="/predictions", tags=["reviews"])


def _get_prediction(db: Session, prediction_id: str) -> Prediction:
    p = db.scalar(select(Prediction).where(Prediction.id == prediction_id)
                  .options(selectinload(Prediction.reviews).selectinload(DoctorReview.doctor)))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prediction not found")
    return p


@router.post("/{prediction_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(prediction_id: str, body: ReviewCreate, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    """Record a doctor's review of an AI result. Reviews are append-only: a correction is a new review and the newest wins."""
    pred = _get_prediction(db, prediction_id)
    latest_id = db.scalar(select(Prediction.id).where(Prediction.image_id == pred.image_id)
                          .order_by(Prediction.created_at.desc(), Prediction.id.desc()).limit(1))
    if latest_id != pred.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This prediction was superseded by a newer analysis of the same image")
    r = DoctorReview(prediction_id=pred.id, doctor_id=doctor.id, decision=body.decision, impression=body.impression,
                     comment=(body.comment or "").strip() or None)
    db.add(r)
    db.flush()
    audit(db, request, doctor.id, "review.create", "prediction", pred.id,
          {"review_id": r.id, "decision": r.decision.value, "image_id": pred.image_id})
    db.commit()
    db.refresh(r)
    return review_out(r)


@router.get("/{prediction_id}/reviews", response_model=list[ReviewOut])
def list_reviews(prediction_id: str, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return [review_out(r) for r in _get_prediction(db, prediction_id).reviews]
