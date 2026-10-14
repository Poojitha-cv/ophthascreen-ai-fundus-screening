# from __future__ import annotations

# from dataclasses import dataclass
# from datetime import date, datetime, time, timezone

# from sqlalchemy import Select, case, func, or_, select
# from sqlalchemy.orm import Session

# from app.core.database import utcnow
# from app.modules.auth.models import User
# from app.modules.dashboard.schemas import (CoreScore, DashboardSummary, QueueItem, QueuePatient, QueueReview, QueueSort, QueueStatus)
# from app.modules.patients.models import Patient
# from app.modules.reviews.models import DoctorReview
# from app.modules.screenings.models import AnalysisStatus, Eye, FundusImage, Prediction, QualityStatus, Screening


# @dataclass
# class QueueFilters:
#     status: QueueStatus = QueueStatus.PENDING_REVIEW
#     eye: Eye | None = None
#     quality: QualityStatus | None = None
#     needs_review: bool | None = None
#     abnormal: bool | None = None          # uses the screening (high-sensitivity) threshold
#     q: str | None = None                  # patient name / MRN
#     patient_id: str | None = None
#     date_from: date | None = None
#     date_to: date | None = None
#     sort: QueueSort = QueueSort.PRIORITY


# def _latest_prediction():
#     rn = func.row_number().over(partition_by=Prediction.image_id, order_by=(Prediction.created_at.desc(), Prediction.id.desc())).label("rn")
#     inner = select(Prediction.id.label("pid"), Prediction.image_id.label("iid"), rn).subquery()
#     return select(inner.c.pid, inner.c.iid).where(inner.c.rn == 1).subquery("lp")


# def _latest_review():
#     rn = func.row_number().over(partition_by=DoctorReview.prediction_id, order_by=(DoctorReview.created_at.desc(), DoctorReview.id.desc())).label("rn")
#     inner = select(DoctorReview.id.label("rid"), DoctorReview.prediction_id.label("prid"), rn).subquery()
#     return select(inner.c.rid, inner.c.prid).where(inner.c.rn == 1).subquery("lr")


# def _query(cols: list, f: QueueFilters) -> Select:
#     lp, lr = _latest_prediction(), _latest_review()
#     stmt = (select(*cols).select_from(FundusImage)
#             .join(Screening, Screening.id == FundusImage.screening_id)
#             .join(Patient, Patient.id == Screening.patient_id)
#             .outerjoin(lp, lp.c.iid == FundusImage.id)
#             .outerjoin(Prediction, Prediction.id == lp.c.pid)
#             .outerjoin(lr, lr.c.prid == Prediction.id)
#             .outerjoin(DoctorReview, DoctorReview.id == lr.c.rid)
#             .outerjoin(User, User.id == DoctorReview.doctor_id)
#             .where(FundusImage.is_current.is_(True)))
#     st = f.status
#     if st == QueueStatus.PENDING_REVIEW:
#         stmt = stmt.where(Prediction.id.is_not(None), DoctorReview.id.is_(None))
#     elif st == QueueStatus.REVIEWED:
#         stmt = stmt.where(DoctorReview.id.is_not(None))
#     elif st == QueueStatus.QUALITY_FAILED:
#         stmt = stmt.where(FundusImage.quality_status == QualityStatus.FAIL)
#     elif st == QueueStatus.ANALYSIS_INCOMPLETE:
#         stmt = stmt.where(FundusImage.analysis_status.in_([AnalysisStatus.PENDING, AnalysisStatus.FAILED]))
#     if f.eye:
#         stmt = stmt.where(FundusImage.eye == f.eye)
#     if f.quality:
#         stmt = stmt.where(FundusImage.quality_status == f.quality)
#     if f.needs_review is not None:
#         stmt = stmt.where(Prediction.needs_review.is_(f.needs_review))
#     if f.abnormal is not None:
#         stmt = stmt.where(Prediction.risk_abnormal_screening.is_(f.abnormal))
#     if f.patient_id:
#         stmt = stmt.where(Patient.id == f.patient_id)
#     if f.q:
#         esc = f.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
#         stmt = stmt.where(or_(Patient.full_name.ilike(f"%{esc}%", escape="\\"), Patient.medical_record_number.ilike(f"{esc}%", escape="\\")))
#     if f.date_from:
#         stmt = stmt.where(FundusImage.uploaded_at >= datetime.combine(f.date_from, time.min, tzinfo=timezone.utc))
#     if f.date_to:
#         stmt = stmt.where(FundusImage.uploaded_at <= datetime.combine(f.date_to, time.max, tzinfo=timezone.utc))
#     return stmt


# def _order(f: QueueFilters) -> list:
#     newest = FundusImage.uploaded_at.desc()
#     risk = Prediction.risk_prob.desc().nulls_last()
#     if f.sort == QueueSort.NEWEST:
#         return [newest, FundusImage.id]
#     if f.sort == QueueSort.RISK:
#         return [risk, newest, FundusImage.id]
#     return [case((Prediction.risk_abnormal_screening.is_(True), 0), else_=1),
#             case((Prediction.needs_review.is_(True), 0), else_=1), risk, newest, FundusImage.id]


# def _item(img: FundusImage, pred: Prediction | None, pat: Patient, rev: DoctorReview | None, doctor_name: str | None) -> QueueItem:
#     top: list[CoreScore] = []
#     if pred is not None:
#         core = pred.model_meta.get("core_classes", [])
#         top = [CoreScore(code=c, probability=round(pred.disease_probs[c], 5))
#                for c in sorted(core, key=lambda c: pred.disease_probs.get(c, 0.0), reverse=True)[:3] if c in pred.disease_probs]
#     return QueueItem(
#         image_id=img.id, screening_id=img.screening_id, prediction_id=pred.id if pred else None,
#         patient=QueuePatient(id=pat.id, full_name=pat.full_name, medical_record_number=pat.medical_record_number,
#                              date_of_birth=pat.date_of_birth, sex=pat.sex),
#         eye=img.eye, uploaded_at=img.uploaded_at, quality_status=img.quality_status,
#         quality_issue_codes=[i["code"] for i in img.quality_report["issues"]], analysis_status=img.analysis_status,
#         risk_probability=round(pred.risk_prob, 5) if pred else None,
#         risk_abnormal_screening=pred.risk_abnormal_screening if pred else None,
#         risk_abnormal_max_f1=pred.risk_abnormal_maxf1 if pred else None,
#         needs_review=pred.needs_review if pred else None,
#         flagged_diseases=list(pred.flagged_diseases) if pred else [], top_core_diseases=top,
#         review_status=None if pred is None else ("reviewed" if rev else "pending"),
#         last_review=QueueReview(decision=rev.decision.value, impression=rev.impression.value if rev.impression else None,
#                                 doctor_name=doctor_name, created_at=rev.created_at) if rev else None)


# def queue(db: Session, f: QueueFilters, offset: int, limit: int) -> tuple[list[QueueItem], int]:
#     total = db.scalar(_query([func.count(FundusImage.id)], f)) or 0
#     stmt = _query([FundusImage, Prediction, Patient, DoctorReview, User.full_name], f).order_by(*_order(f)).offset(offset).limit(limit)
#     return [_item(*row) for row in db.execute(stmt).all()], total


# def summary(db: Session) -> DashboardSummary:
#     def n(**kw) -> int:
#         return db.scalar(_query([func.count(FundusImage.id)], QueueFilters(**kw))) or 0

#     today_start = datetime.combine(utcnow().date(), time.min, tzinfo=timezone.utc)
#     return DashboardSummary(
#         generated_at=utcnow(),
#         patients_total=db.scalar(select(func.count(Patient.id))) or 0,
#         screenings_total=db.scalar(select(func.count(Screening.id))) or 0,
#         current_images_total=n(status=QueueStatus.ALL),
#         pending_review=n(status=QueueStatus.PENDING_REVIEW),
#         pending_flagged_abnormal=n(status=QueueStatus.PENDING_REVIEW, abnormal=True),
#         pending_model_uncertain=n(status=QueueStatus.PENDING_REVIEW, needs_review=True),
#         reviewed_total=n(status=QueueStatus.REVIEWED),
#         reviewed_today_utc=db.scalar(select(func.count(DoctorReview.id)).where(DoctorReview.created_at >= today_start)) or 0,
#         quality_failed=n(status=QueueStatus.QUALITY_FAILED),
#         analysis_incomplete=n(status=QueueStatus.ANALYSIS_INCOMPLETE))


from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.modules.auth.models import User
from app.modules.dashboard.schemas import (CoreScore, DashboardSummary, QueueItem, QueuePatient, QueueReview, QueueSort, QueueStatus)
from app.modules.inference.rfmid_labels import RFMID_NAMES
from app.modules.patients.models import Patient
from app.modules.reviews.models import DoctorReview
from app.modules.screenings.models import AnalysisStatus, Eye, FundusImage, Prediction, QualityStatus, Screening


@dataclass
class QueueFilters:
    status: QueueStatus = QueueStatus.PENDING_REVIEW
    eye: Eye | None = None
    quality: QualityStatus | None = None
    needs_review: bool | None = None
    abnormal: bool | None = None          # uses the screening (high-sensitivity) threshold
    q: str | None = None                  # patient name / MRN
    patient_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: QueueSort = QueueSort.PRIORITY


def _latest_prediction():
    rn = func.row_number().over(partition_by=Prediction.image_id, order_by=(Prediction.created_at.desc(), Prediction.id.desc())).label("rn")
    inner = select(Prediction.id.label("pid"), Prediction.image_id.label("iid"), rn).subquery()
    return select(inner.c.pid, inner.c.iid).where(inner.c.rn == 1).subquery("lp")


def _latest_review():
    rn = func.row_number().over(partition_by=DoctorReview.prediction_id, order_by=(DoctorReview.created_at.desc(), DoctorReview.id.desc())).label("rn")
    inner = select(DoctorReview.id.label("rid"), DoctorReview.prediction_id.label("prid"), rn).subquery()
    return select(inner.c.rid, inner.c.prid).where(inner.c.rn == 1).subquery("lr")


def _query(cols: list, f: QueueFilters) -> Select:
    lp, lr = _latest_prediction(), _latest_review()
    stmt = (select(*cols).select_from(FundusImage)
            .join(Screening, Screening.id == FundusImage.screening_id)
            .join(Patient, Patient.id == Screening.patient_id)
            .outerjoin(lp, lp.c.iid == FundusImage.id)
            .outerjoin(Prediction, Prediction.id == lp.c.pid)
            .outerjoin(lr, lr.c.prid == Prediction.id)
            .outerjoin(DoctorReview, DoctorReview.id == lr.c.rid)
            .outerjoin(User, User.id == DoctorReview.doctor_id)
            .where(FundusImage.is_current.is_(True)))
    st = f.status
    if st == QueueStatus.PENDING_REVIEW:
        stmt = stmt.where(Prediction.id.is_not(None), DoctorReview.id.is_(None))
    elif st == QueueStatus.REVIEWED:
        stmt = stmt.where(DoctorReview.id.is_not(None))
    elif st == QueueStatus.QUALITY_FAILED:
        stmt = stmt.where(FundusImage.quality_status == QualityStatus.FAIL)
    elif st == QueueStatus.ANALYSIS_INCOMPLETE:
        stmt = stmt.where(FundusImage.analysis_status.in_([AnalysisStatus.PENDING, AnalysisStatus.FAILED]))
    if f.eye:
        stmt = stmt.where(FundusImage.eye == f.eye)
    if f.quality:
        stmt = stmt.where(FundusImage.quality_status == f.quality)
    if f.needs_review is not None:
        stmt = stmt.where(Prediction.needs_review.is_(f.needs_review))
    if f.abnormal is not None:
        stmt = stmt.where(Prediction.risk_abnormal_screening.is_(f.abnormal))
    if f.patient_id:
        stmt = stmt.where(Patient.id == f.patient_id)
    if f.q:
        esc = f.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(or_(Patient.full_name.ilike(f"%{esc}%", escape="\\"), Patient.medical_record_number.ilike(f"{esc}%", escape="\\")))
    if f.date_from:
        stmt = stmt.where(FundusImage.uploaded_at >= datetime.combine(f.date_from, time.min, tzinfo=timezone.utc))
    if f.date_to:
        stmt = stmt.where(FundusImage.uploaded_at <= datetime.combine(f.date_to, time.max, tzinfo=timezone.utc))
    return stmt


def _order(f: QueueFilters) -> list:
    newest = FundusImage.uploaded_at.desc()
    risk = Prediction.risk_prob.desc().nulls_last()
    if f.sort == QueueSort.NEWEST:
        return [newest, FundusImage.id]
    if f.sort == QueueSort.RISK:
        return [risk, newest, FundusImage.id]
    return [case((Prediction.risk_abnormal_screening.is_(True), 0), else_=1),
            case((Prediction.needs_review.is_(True), 0), else_=1), risk, newest, FundusImage.id]


def _item(img: FundusImage, pred: Prediction | None, pat: Patient, rev: DoctorReview | None, doctor_name: str | None) -> QueueItem:
    top: list[CoreScore] = []
    if pred is not None:
        core = pred.model_meta.get("core_classes", [])
        top = [CoreScore(code=c, name=RFMID_NAMES.get(c), probability=round(pred.disease_probs[c], 5))
               for c in sorted(core, key=lambda c: pred.disease_probs.get(c, 0.0), reverse=True)[:3] if c in pred.disease_probs]
    return QueueItem(
        image_id=img.id, screening_id=img.screening_id, prediction_id=pred.id if pred else None,
        patient=QueuePatient(id=pat.id, full_name=pat.full_name, medical_record_number=pat.medical_record_number,
                             date_of_birth=pat.date_of_birth, sex=pat.sex),
        eye=img.eye, uploaded_at=img.uploaded_at, quality_status=img.quality_status,
        quality_issue_codes=[i["code"] for i in img.quality_report["issues"]], analysis_status=img.analysis_status,
        risk_probability=round(pred.risk_prob, 5) if pred else None,
        risk_abnormal_screening=pred.risk_abnormal_screening if pred else None,
        risk_abnormal_max_f1=pred.risk_abnormal_maxf1 if pred else None,
        needs_review=pred.needs_review if pred else None,
        flagged_diseases=list(pred.flagged_diseases) if pred else [],
        flagged_disease_names={c: RFMID_NAMES[c] for c in pred.flagged_diseases if c in RFMID_NAMES} if pred else {},
        top_core_diseases=top,
        review_status=None if pred is None else ("reviewed" if rev else "pending"),
        last_review=QueueReview(decision=rev.decision.value, impression=rev.impression.value if rev.impression else None,
                                doctor_name=doctor_name, created_at=rev.created_at) if rev else None)


def queue(db: Session, f: QueueFilters, offset: int, limit: int) -> tuple[list[QueueItem], int]:
    total = db.scalar(_query([func.count(FundusImage.id)], f)) or 0
    stmt = _query([FundusImage, Prediction, Patient, DoctorReview, User.full_name], f).order_by(*_order(f)).offset(offset).limit(limit)
    return [_item(*row) for row in db.execute(stmt).all()], total


def summary(db: Session) -> DashboardSummary:
    def n(**kw) -> int:
        return db.scalar(_query([func.count(FundusImage.id)], QueueFilters(**kw))) or 0

    today_start = datetime.combine(utcnow().date(), time.min, tzinfo=timezone.utc)
    return DashboardSummary(
        generated_at=utcnow(),
        patients_total=db.scalar(select(func.count(Patient.id))) or 0,
        screenings_total=db.scalar(select(func.count(Screening.id))) or 0,
        current_images_total=n(status=QueueStatus.ALL),
        pending_review=n(status=QueueStatus.PENDING_REVIEW),
        pending_flagged_abnormal=n(status=QueueStatus.PENDING_REVIEW, abnormal=True),
        pending_model_uncertain=n(status=QueueStatus.PENDING_REVIEW, needs_review=True),
        reviewed_total=n(status=QueueStatus.REVIEWED),
        reviewed_today_utc=db.scalar(select(func.count(DoctorReview.id)).where(DoctorReview.created_at >= today_start)) or 0,
        quality_failed=n(status=QueueStatus.QUALITY_FAILED),
        analysis_incomplete=n(status=QueueStatus.ANALYSIS_INCOMPLETE))
