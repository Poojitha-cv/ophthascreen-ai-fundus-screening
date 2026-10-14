"""ORM -> API schemas for the clinical / risk layer, applying role-based visibility in one place."""
from __future__ import annotations

from app.core.config import Settings
from app.modules.auth.models import Role, User
from app.modules.risk.models import ClinicalRecord, ScreeningRisk
from app.modules.risk.schemas import ClinicalOut, RiskOut


def clinical_out(rec: ClinicalRecord | None) -> ClinicalOut | None:
    return ClinicalOut.model_validate(rec) if rec is not None else None


def can_see_risk(viewer: User, settings: Settings) -> bool:
    """Same policy as the raw AI output: doctors always; patients only if OPH_PATIENT_CAN_SEE_AI_RESULTS is on."""
    return viewer.role == Role.DOCTOR or settings.patient_can_see_ai_results


def risk_out(row: ScreeningRisk | None, viewer: User, settings: Settings) -> RiskOut | None:
    if row is None or not can_see_risk(viewer, settings):
        return None
    return RiskOut.model_validate({**row.result, "id": row.id, "screening_id": row.screening_id, "created_at": row.created_at,
                                   "trigger": row.trigger, "inputs": row.inputs})
