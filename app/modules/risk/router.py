from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import Settings
from app.core.deps import get_current_user, get_db, get_settings_dep, require_doctor
from app.modules.auth.models import User
from app.modules.risk import service
from app.modules.risk.assess import default_rules
from app.modules.risk.schemas import ClinicalIn, ClinicalOut, ClinicalSaveOut, RiskOut
from app.modules.risk.serializers import can_see_risk, clinical_out, risk_out
from app.modules.screenings.service import get_accessible_screening

router = APIRouter(tags=["clinical & risk"])


@router.post("/screenings/{screening_id}/clinical", response_model=ClinicalSaveOut)
def save_clinical(screening_id: str, body: ClinicalIn, request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)):
    """Create or update the clinical record of a screening, then re-assess risk. Fields present in the body are set
    (null = clear); omitted fields are left unchanged. Patients may report symptoms/history for their own screenings;
    visual acuity, IOP and cup-to-disc ratio are doctor-only."""
    screening = get_accessible_screening(db, user, screening_id)
    service.ensure_may_enter(body, user)
    rec, changed = service.save_clinical(db, screening, body, user, request)
    db.commit()
    row = service.refresh_risk(db, screening.id, user.id, "clinical_updated")
    db.commit()
    return ClinicalSaveOut(clinical=clinical_out(rec), risk=risk_out(row, user, settings), changed_fields=changed)


@router.get("/screenings/{screening_id}/clinical", response_model=ClinicalOut | None)
def get_clinical(screening_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_accessible_screening(db, user, screening_id)
    audit(db, request, user.id, "clinical.view", "screening", s.id)
    db.commit()
    return clinical_out(service.get_clinical(db, s.id))


@router.get("/screenings/{screening_id}/risk", response_model=RiskOut)
def get_risk(screening_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings_dep)):
    """Current risk assessment with its drivers, decision path, data gaps and warnings (doctors; patients only if policy allows)."""
    s = get_accessible_screening(db, user, screening_id)
    if not can_see_risk(user, settings):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Risk results are not available to patients")
    row = service.current_risk(db, s.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No risk assessment has been computed for this screening yet")
    audit(db, request, user.id, "risk.view", "screening", s.id, {"risk_id": row.id})
    db.commit()
    return risk_out(row, user, settings)


@router.post("/screenings/{screening_id}/risk/recompute", response_model=RiskOut)
def recompute_risk(screening_id: str, request: Request, doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings_dep)):
    """Re-run the rules on the stored inputs (e.g. after the rules file changed). Appends a new result only if something changed."""
    s = get_accessible_screening(db, doctor, screening_id)
    row = service.compute_risk(db, s.id, doctor.id, "manual")
    audit(db, request, doctor.id, "risk.recompute", "screening", s.id, {"risk_id": row.id})
    db.commit()
    return risk_out(row, doctor, settings)


@router.get("/risk/rules")
def get_rules(doctor: User = Depends(require_doctor)):
    """The active, versioned rules (every cutoff, point value, red flag, matrix cell and override) with their evidence labels."""
    r = default_rules()
    return {"rules_version": r.version, "rules_sha256": r.sha256, "rules": r.data}
