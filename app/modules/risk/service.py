"""Glue between the database and the pure risk function (assess.py).

This module reads the screening, its current images, their latest ConvNeXt predictions and the clinical record, hands them
to assess_risk(), and stores the result. It never runs or modifies the ConvNeXt model: it only reads stored Prediction rows.

Must not import app.modules.screenings.service (that module calls this one).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from enum import Enum

from fastapi import HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import utcnow
from app.modules.auth.models import Role, User
from app.modules.patients.models import Patient
from app.modules.risk.assess import ClinicalInput, EyeImageInput, RiskRules, assess_risk, default_rules
from app.modules.risk.models import ClinicalRecord, ScreeningRisk
from app.modules.risk.schemas import CLINICAL_FIELDS, MEASUREMENT_FIELDS, ClinicalIn
from app.modules.screenings.models import FundusImage, Prediction, Screening

log = logging.getLogger(__name__)


# ---------- clinical record ----------

def get_clinical(db: Session, screening_id: str) -> ClinicalRecord | None:
    return db.scalar(select(ClinicalRecord).where(ClinicalRecord.screening_id == screening_id))


def parse_clinical_json(raw: str | None, user: User) -> ClinicalIn | None:
    """For the optional `clinical` multipart field of POST /patients/{id}/screenings. Validates and applies role rules
    BEFORE anything is written."""
    if raw is None or not raw.strip():
        return None
    try:
        payload = ClinicalIn.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, _validation_message(exc, "clinical"))
    ensure_may_enter(payload, user)
    return payload if payload.model_fields_set else None


def ensure_may_enter(payload: ClinicalIn, user: User) -> None:
    """Patients may report symptoms and history; visual acuity, IOP and cup-to-disc ratio are measurements only a doctor enters."""
    if user.role != Role.DOCTOR and any(f in payload.model_fields_set for f in MEASUREMENT_FIELDS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Visual acuity, IOP and cup-to-disc ratio can only be entered by a doctor")


def _validation_message(exc: ValidationError, prefix: str) -> str:
    return "; ".join(f"{prefix}.{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" if e["loc"] else f"{prefix}: {e['msg']}" for e in exc.errors())


def _plain(v):
    return v.value if isinstance(v, Enum) else v


def save_clinical(db: Session, screening: Screening, payload: ClinicalIn, user: User, request: Request | None) -> tuple[ClinicalRecord, list[str]]:
    """Create or merge-update the screening's clinical record. Fields present in the payload are set (null clears a value);
    omitted fields are left unchanged. Does not commit. Returns (record, names of fields that changed)."""
    data = {k: _plain(v) for k, v in payload.model_dump(exclude_unset=True).items()}
    if not data:
        raise HTTPException(422, "No clinical fields provided")
    rec = get_clinical(db, screening.id)
    current = {f: getattr(rec, f) for f in CLINICAL_FIELDS} if rec else {}
    try:
        merged = ClinicalIn.model_validate({**current, **data})          # re-validate the combined record (e.g. duration vs diabetes)
    except ValidationError as exc:
        raise HTTPException(422, _validation_message(exc, "clinical"))
    values = {k: _plain(v) for k, v in merged.model_dump().items()}
    changed = sorted(k for k, v in data.items() if (current.get(k) if rec else None) != v)
    created = rec is None
    if created:
        rec = ClinicalRecord(screening_id=screening.id, recorded_by=user.id, **values)
        db.add(rec)
    elif changed:
        for k, v in values.items():
            setattr(rec, k, v)
        rec.recorded_by = user.id
        rec.updated_at = utcnow()
    db.flush()
    if created or changed:
        audit(db, request, user.id, "clinical.upsert", "screening", screening.id, {"created": created, "fields": changed})
    return rec, changed


def _clinical_input(rec: ClinicalRecord | None) -> ClinicalInput | None:
    if rec is None:
        return None
    return ClinicalInput(**{f: getattr(rec, f) for f in CLINICAL_FIELDS})


# ---------- building inputs for the pure function ----------

def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _eye_inputs(db: Session, screening_id: str, rules: RiskRules) -> tuple[dict[str, EyeImageInput | None], dict]:
    """Current image of each eye + its latest stored prediction. Thresholds come from the prediction's own model_meta."""
    low_key, high_key = rules.data["image"]["low_threshold_source"], rules.data["image"]["high_threshold_source"]
    eyes: dict[str, EyeImageInput | None] = {"right": None, "left": None}
    trace: dict[str, dict | None] = {"right": None, "left": None}
    imgs = db.scalars(select(FundusImage).where(FundusImage.screening_id == screening_id, FundusImage.is_current.is_(True))
                      .order_by(FundusImage.uploaded_at.desc(), FundusImage.id.desc())).all()
    for img in imgs:
        eye = img.eye.value
        if eyes.get(eye) is not None:
            continue                                   # newest current image per eye wins
        pred = db.scalars(select(Prediction).where(Prediction.image_id == img.id)
                          .order_by(Prediction.created_at.desc(), Prediction.id.desc()).limit(1)).first()
        common = dict(quality_status=img.quality_status.value, analysis_status=img.analysis_status.value, image_id=img.id,
                      quality_issue_codes=tuple(i["code"] for i in (img.quality_report or {}).get("issues", [])))
        if pred is None:
            eyes[eye] = EyeImageInput(**common)
            trace[eye] = {"image_id": img.id, "prediction_id": None}
            continue
        meta = pred.model_meta or {}
        eyes[eye] = EyeImageInput(**common, risk_prob=pred.risk_prob, thr_screening=meta.get(low_key), thr_max_f1=meta.get(high_key),
                                  needs_review=pred.needs_review, crop_ok=pred.crop_ok, model_warnings=tuple(pred.warnings or ()),
                                  prediction_id=pred.id)
        trace[eye] = {"image_id": img.id, "prediction_id": pred.id, "model_tag": pred.model_tag, "model_weights_sha256": pred.model_weights_sha256}
    return eyes, trace


def _eye_snapshot(inp: EyeImageInput | None, trace: dict | None) -> dict | None:
    if inp is None:
        return None
    snap = asdict(inp)
    snap.update({k: v for k, v in (trace or {}).items() if k not in snap})      # model tag / weights hash for traceability
    return snap


def _norm(obj) -> dict:
    """JSON round-trip so a freshly built snapshot compares equal to one read back from the database."""
    return json.loads(json.dumps(obj, default=str))


def _assess_for(db: Session, screening_id: str, rules: RiskRules):
    screening = db.get(Screening, screening_id)
    patient = db.get(Patient, screening.patient_id)
    age = age_on(patient.date_of_birth, screening.created_at.date())
    clinical = _clinical_input(get_clinical(db, screening_id))
    eyes, trace = _eye_inputs(db, screening_id, rules)
    result = assess_risk(clinical, eyes, age_years=age, rules=rules)
    inputs = _norm({"age_years": age, "clinical": asdict(clinical) if clinical else None,
                    "eyes": {e: _eye_snapshot(v, trace[e]) for e, v in eyes.items()}})
    return result, inputs


def _persist(db: Session, screening_id: str, user_id: str | None, trigger: str, result, inputs: dict) -> ScreeningRisk:
    cur = current_risk(db, screening_id)
    if cur is not None and cur.inputs == inputs and cur.rules_sha256 == result.rules_sha256:
        return cur                                       # nothing changed: do not append a duplicate row
    db.execute(update(ScreeningRisk).where(ScreeningRisk.screening_id == screening_id, ScreeningRisk.is_current.is_(True)).values(is_current=False))
    row = ScreeningRisk(screening_id=screening_id, computed_by=user_id, trigger=trigger, is_current=True, rules_version=result.rules_version,
                        rules_sha256=result.rules_sha256, tier=result.tier, clinical_status=result.clinical_status,
                        inputs=inputs, result=_norm(result.to_dict()))
    db.add(row)
    db.flush()
    return row


def compute_risk(db: Session, screening_id: str, user_id: str | None, trigger: str, rules: RiskRules | None = None) -> ScreeningRisk:
    """Assess and store. Raises on failure (used by the explicit recompute endpoint)."""
    result, inputs = _assess_for(db, screening_id, rules or default_rules())
    return _persist(db, screening_id, user_id, trigger, result, inputs)


def refresh_risk(db: Session, screening_id: str, user_id: str | None, trigger: str) -> ScreeningRisk | None:
    """Same as compute_risk but never raises from the assessment itself: uploads, re-analysis and clinical saves have
    already stored their data, and a bug in the risk layer must not turn them into a 500. Returns None on failure."""
    try:
        result, inputs = _assess_for(db, screening_id, default_rules())
    except Exception:
        log.exception("Risk assessment failed for screening %s (trigger=%s)", screening_id, trigger)
        return None
    return _persist(db, screening_id, user_id, trigger, result, inputs)


# ---------- reading ----------

def current_risk(db: Session, screening_id: str) -> ScreeningRisk | None:
    return db.scalar(select(ScreeningRisk).where(ScreeningRisk.screening_id == screening_id, ScreeningRisk.is_current.is_(True))
                     .order_by(ScreeningRisk.created_at.desc(), ScreeningRisk.id.desc()).limit(1))


def extras_for(db: Session, screening_ids: list[str]) -> dict[str, tuple[ClinicalRecord | None, ScreeningRisk | None]]:
    """Batch-load clinical record + current risk for several screenings (avoids one query pair per screening)."""
    if not screening_ids:
        return {}
    recs = {r.screening_id: r for r in db.scalars(select(ClinicalRecord).where(ClinicalRecord.screening_id.in_(screening_ids)))}
    risks: dict[str, ScreeningRisk] = {}
    for r in db.scalars(select(ScreeningRisk).where(ScreeningRisk.screening_id.in_(screening_ids), ScreeningRisk.is_current.is_(True))
                        .order_by(ScreeningRisk.created_at.asc(), ScreeningRisk.id.asc())):
        risks[r.screening_id] = r                         # ascending order: the newest row overwrites
    return {sid: (recs.get(sid), risks.get(sid)) for sid in screening_ids}
