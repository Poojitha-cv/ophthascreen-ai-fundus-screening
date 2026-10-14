"""Pure risk assessment: ConvNeXt image output + clinical factors -> Low / Moderate / High.

No database, no I/O (apart from loading the rules file), no model imports. Every cutoff, point value, cap,
band, red flag, matrix cell and override comes from risk_rules_v1.json; this module only evaluates them.

HEURISTIC / UNVALIDATED. See docs/RISK_ASSESSMENT.md for what is validated (the image model's discrimination and
its two thresholds, on RFMiD) and what is a design choice (everything else). The result is a prioritisation aid
for clinician review, never a diagnosis.
"""
from __future__ import annotations

import hashlib
import json
import math
import operator
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

RULES_PATH = Path(__file__).with_name("risk_rules_v1.json")
EYES = ("right", "left")                                   # evaluation / display order
EYE_LABEL = {"right": "Right eye (OD)", "left": "Left eye (OS)"}
INCOMPLETE = "Incomplete"                                  # patient-level result when no eye has a usable image
NOTICE = ("Heuristic, unvalidated risk indicator for clinician prioritisation. Not a diagnosis; it never replaces "
          "examination or review by a qualified clinician.")

PER_EYE_MEASUREMENTS = ("iop", "cdr", "va")
BOOL_FIELDS = ("diabetes", "hypertension", "blurred_vision", "floaters", "visual_field_loss", "eye_pain",
               "visual_distortion", "family_history_glaucoma", "family_history_diabetic_retinopathy", "family_history_amd")
PATIENT_RAW_FIELDS = BOOL_FIELDS + ("previous_eye_condition",)
_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}
_VALID_OPS = set(_OPS) | {"true", "in"}

_NOT_ASSESSED_TEXT = {
    "no_image": "no image was uploaded for this eye",
    "quality_failed": "the image failed the quality check (retake needed)",
    "analysis_not_completed": "the image has no completed model analysis",
    "fundus_not_found": "the model found no fundus region in the image",
    "invalid_model_output": "the stored model output or thresholds are invalid",
}


# --------------------------------------------------------------------------- inputs

@dataclass(frozen=True)
class ClinicalInput:
    """All fields optional: None means 'not recorded' (never silently imputed)."""
    diabetes: bool | None = None
    diabetes_duration_years: int | None = None
    hypertension: bool | None = None
    blurred_vision: bool | None = None
    floaters: bool | None = None
    visual_field_loss: bool | None = None
    eye_pain: bool | None = None
    visual_distortion: bool | None = None
    family_history_glaucoma: bool | None = None
    family_history_diabetic_retinopathy: bool | None = None
    family_history_amd: bool | None = None
    previous_eye_condition: str | None = None       # none | cataract | glaucoma | amd | diabetic_retinopathy | other
    previous_eye_surgery: bool | None = None        # recorded for the doctor; not used by the rules
    va_od: float | None = None                      # decimal visual acuity
    va_os: float | None = None
    iop_od: float | None = None                     # mmHg
    iop_os: float | None = None
    cdr_od: float | None = None                     # cup-to-disc ratio
    cdr_os: float | None = None


@dataclass(frozen=True)
class EyeImageInput:
    """What the pipeline knows about one eye's current image (the ConvNeXt output is not re-computed here)."""
    quality_status: str = "pass"                    # pass | warn | fail
    analysis_status: str = "completed"              # completed | pending | failed | skipped_quality
    risk_prob: float | None = None                  # Disease_Risk probability
    thr_screening: float | None = None              # model's screening threshold (from the stored prediction meta)
    thr_max_f1: float | None = None                 # model's max-F1 threshold
    needs_review: bool | None = None
    crop_ok: bool | None = True
    model_warnings: tuple[str, ...] = ()
    quality_issue_codes: tuple[str, ...] = ()
    image_id: str | None = None
    prediction_id: str | None = None


# --------------------------------------------------------------------------- outputs

@dataclass(frozen=True)
class Note:
    code: str
    message: str
    eye: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class Driver:
    kind: str                 # image | clinical | red_flag | combination | override
    id: str
    label: str
    evidence: str             # rfmid_validated | conventional_reference | heuristic
    effect: str
    scope: str = "eye"        # eye | patient  (patient-level factors are scored on both eyes)
    eye: str | None = None
    value: Any = None
    points: int | None = None


@dataclass(frozen=True)
class EyeResult:
    eye: str
    state: str                                           # assessed | not_assessed
    not_assessed_reason: str | None = None
    image_band: str | None = None
    risk_prob: float | None = None
    thr_screening: float | None = None
    thr_max_f1: float | None = None
    needs_review: bool | None = None
    clinical_score: int = 0
    clinical_max_score: int = 0
    clinical_domain_scores: dict = field(default_factory=dict)
    clinical_band: str = "C0"
    red_flags: list = field(default_factory=list)        # ids of fired red flags
    matrix_tier: str | None = None
    tier: str | None = None                              # None when not assessed
    overrides_applied: list = field(default_factory=list)
    drivers: list = field(default_factory=list)


@dataclass(frozen=True)
class RiskAssessment:
    rules_version: str
    rules_sha256: str
    tier: str                                            # Low | Moderate | High | Incomplete
    tier_driven_by: str | None                           # eye whose tier set the patient tier
    clinical_status: str                                 # complete | incomplete | not_provided
    eyes: dict = field(default_factory=dict)             # eye -> EyeResult
    patient_drivers: list = field(default_factory=list)
    decision_path: list = field(default_factory=list)
    data_gaps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notice: str = NOTICE
    rules_status: str = ""                               # copied from the rules file so a stored result is self-explanatory
    evidence_legend: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- rules

class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class RiskRules:
    data: dict
    sha256: str

    @property
    def version(self) -> str:
        return self.data["rules_version"]


def _derived_names(data: dict) -> set[str]:
    return set(data["clinical"]["derived_facts"])


def _fact_names(data: dict) -> tuple[set[str], set[str]]:
    """(per-eye fact names, patient-level fact names)."""
    per_eye = set(PER_EYE_MEASUREMENTS)
    patient = set(PATIENT_RAW_FIELDS) | {"diabetes_duration_years", "age"} | _derived_names(data)
    return per_eye, patient


def validate_rules(data: dict) -> None:
    """Structural validation so a typo in the JSON fails loudly at load time, not silently at assessment time."""
    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise RulesError(msg)

    for key in ("rules_version", "tiers", "eyes", "image", "clinical", "combination"):
        need(key in data, f"missing top-level key {key!r}")
    tiers = data["tiers"]
    need(len(tiers) == 3 and len(set(tiers)) == 3, "tiers must be 3 distinct names, lowest first")
    need(set(data["eyes"]) == set(EYES) and set(data["eyes"].values()) == {"od", "os"}, "eyes must map right/left to od/os")
    img = data["image"]
    need(set(img.get("bands", {})) == {"I0", "I1", "I2"} and set(img.get("evidence", {})) == {"I0", "I1", "I2"}, "image bands must be I0, I1, I2")
    need(bool(img.get("low_threshold_source")) and bool(img.get("high_threshold_source")), "image threshold sources are required")

    per_eye, patient = _fact_names(data)
    facts = per_eye | patient
    clin = data["clinical"]
    sources = set(PATIENT_RAW_FIELDS) | {f"{m}_{s}" for m in PER_EYE_MEASUREMENTS for s in ("od", "os")}
    for name, spec in clin["derived_facts"].items():
        need(("any_true" in spec) != ("abs_diff" in spec), f"derived fact {name!r} needs exactly one of any_true / abs_diff")
        refs = spec.get("any_true") or spec.get("abs_diff")
        need(all(r in sources for r in refs), f"derived fact {name!r} references unknown source fields")

    def check_cond(c: dict, where: str) -> None:
        need(c.get("fact") in facts, f"{where}: unknown fact {c.get('fact')!r}")
        need(c.get("op") in _VALID_OPS, f"{where}: unknown operator {c.get('op')!r}")
        if c["op"] not in ("true",):
            need("value" in c, f"{where}: operator {c['op']!r} needs a value")

    ids: set[str] = set()
    need(set(clin["domains"]) == {"A", "B", "C", "D"}, "clinical domains must be A, B, C, D")
    for dkey, dom in clin["domains"].items():
        need(isinstance(dom.get("cap"), int) and dom["cap"] > 0, f"domain {dkey}: cap must be a positive integer")
        for item in dom["items"]:
            check_cond(item, f"item {item.get('id')}")
            need(isinstance(item.get("points"), int) and item["points"] > 0, f"item {item.get('id')}: points must be a positive integer")
            need(item["id"] not in ids, f"duplicate id {item['id']!r}")
            ids.add(item["id"])
            need(item.get("evidence") in data["evidence_legend"], f"item {item['id']}: unknown evidence label")
    b = clin["bands"]
    need(0 < b["C1_min_score"] < b["C2_min_score"] <= sum(d["cap"] for d in clin["domains"].values()), "clinical band cut-offs must be increasing and reachable")
    for rf in clin["red_flags"]:
        need(rf["id"] not in ids, f"duplicate id {rf['id']!r}")
        ids.add(rf["id"])
        need(rf.get("scope") in ("eye", "patient"), f"red flag {rf['id']}: scope must be eye or patient")
        need(rf.get("all") or rf.get("any_eye"), f"red flag {rf['id']}: needs 'all' and/or 'any_eye' conditions")
        for c in rf.get("all", []):
            check_cond(c, f"red flag {rf['id']}")
            if rf["scope"] == "patient":
                need(c["fact"] in patient, f"red flag {rf['id']}: patient-scope 'all' conditions must use patient-level facts")
        for c in rf.get("any_eye", []):
            check_cond(c, f"red flag {rf['id']}")
        need(rf["scope"] == "patient" or not rf.get("any_eye"), f"red flag {rf['id']}: 'any_eye' only makes sense with scope 'patient'")

    comb = data["combination"]
    for ib in ("I0", "I1", "I2"):
        need(set(comb["matrix"].get(ib, {})) == {"C0", "C1", "C2"}, f"matrix row {ib} must have C0, C1, C2")
        need(all(t in tiers for t in comb["matrix"][ib].values()), f"matrix row {ib} contains an unknown tier")
    for k in ("model_needs_review_min_tier", "unassessed_eye_clinical_c2_min_tier"):
        need(comb["overrides"].get(k) in tiers, f"override {k} must be a known tier")


def load_rules(path: Path | str | None = None) -> RiskRules:
    raw = Path(path or RULES_PATH).read_bytes()
    data = json.loads(raw)
    validate_rules(data)
    return RiskRules(data=data, sha256=hashlib.sha256(raw).hexdigest())


@lru_cache(maxsize=1)
def default_rules() -> RiskRules:
    return load_rules()


# --------------------------------------------------------------------------- fact resolution

def _cond(value: Any, op: str, ref: Any = None) -> bool | None:
    """True / False, or None when the fact is unknown (unknown never fires a rule)."""
    if value is None:
        return None
    if op == "true":
        return value is True
    if op == "in":
        return value in ref
    return bool(_OPS[op](value, ref))


def _all(vals: list[bool | None]) -> bool | None:
    if any(v is False for v in vals):
        return False
    return True if all(v is True for v in vals) else None


def _any(vals: list[bool | None]) -> bool | None:
    if any(v is True for v in vals):
        return True
    return False if all(v is False for v in vals) else None


def _sources(c: ClinicalInput, age: int | None, rules: RiskRules) -> dict[str, Any]:
    src: dict[str, Any] = {n: getattr(c, n) for n in PATIENT_RAW_FIELDS}
    for m in PER_EYE_MEASUREMENTS:
        for suf in rules.data["eyes"].values():
            src[f"{m}_{suf}"] = getattr(c, f"{m}_{suf}")
    src["age"] = age
    if c.diabetes is False:
        src["diabetes_duration_years"] = 0                  # no diabetes -> no duration to score
    elif c.diabetes is True:
        src["diabetes_duration_years"] = c.diabetes_duration_years
    else:
        src["diabetes_duration_years"] = None
    return src


def _patient_facts(src: dict[str, Any], rules: RiskRules) -> dict[str, Any]:
    facts = {n: v for n, v in src.items() if n in set(PATIENT_RAW_FIELDS) | {"age", "diabetes_duration_years"}}
    for name, spec in rules.data["clinical"]["derived_facts"].items():
        if "any_true" in spec:
            vals = [src[n] for n in spec["any_true"]]
            facts[name] = True if any(v is True for v in vals) else (False if all(v is False for v in vals) else None)
        else:
            a, b = (src[n] for n in spec["abs_diff"])
            facts[name] = None if a is None or b is None else round(abs(a - b), spec.get("decimals", 4))
    return facts


def _eye_facts(src: dict[str, Any], eye: str, rules: RiskRules) -> dict[str, Any]:
    suf = rules.data["eyes"][eye]
    return {m: src[f"{m}_{suf}"] for m in PER_EYE_MEASUREMENTS}


def _data_gaps(c: ClinicalInput | None, src: dict[str, Any], rules: RiskRules) -> tuple[list[Note], str]:
    if c is None:
        return [Note("clinical_not_provided", "No clinical record was provided; clinical factors were not scored.")], "not_provided"
    required = list(PATIENT_RAW_FIELDS) + ["age"]
    if c.diabetes is True:
        required.append("diabetes_duration_years")
    gaps = [Note("missing_clinical_field", f"{n} not recorded; factors that depend on it were not scored.", field=n)
            for n in required if src[n] is None]
    inv = {v: k for k, v in rules.data["eyes"].items()}
    for m in PER_EYE_MEASUREMENTS:
        for suf in rules.data["eyes"].values():
            if src[f"{m}_{suf}"] is None:
                gaps.append(Note("missing_clinical_field", f"{m}_{suf} not recorded; factors that depend on it were not scored.",
                                 eye=inv[suf], field=f"{m}_{suf}"))
    return gaps, ("incomplete" if gaps else "complete")


# --------------------------------------------------------------------------- per-eye evaluation

def _image_eval(inp: EyeImageInput | None, rules: RiskRules) -> tuple[str | None, str | None]:
    """-> (not_assessed_reason, image_band)."""
    if inp is None:
        return "no_image", None
    if inp.quality_status == "fail":
        return "quality_failed", None
    if inp.analysis_status != "completed" or inp.risk_prob is None:
        return "analysis_not_completed", None
    if inp.crop_ok is False:
        return "fundus_not_found", None
    p, lo, hi = inp.risk_prob, inp.thr_screening, inp.thr_max_f1
    if (lo is None or hi is None or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (p, lo, hi))
            or not 0.0 <= p <= 1.0 or lo > hi):
        return "invalid_model_output", None
    return None, ("I2" if p >= hi else "I1" if p >= lo else "I0")


def _score_domains(ctx: dict[str, Any], rules: RiskRules, eye: str) -> tuple[dict, list[Driver], int, int]:
    domain_scores: dict[str, dict] = {}
    drivers: list[Driver] = []
    total = max_total = 0
    per_eye_facts = set(PER_EYE_MEASUREMENTS)
    for dkey, dom in rules.data["clinical"]["domains"].items():
        fired = [it for it in dom["items"] if _cond(ctx[it["fact"]], it["op"], it.get("value"))]
        best: dict[str, dict] = {}                           # exclusive groups: only the highest-point item counts
        counted: list[dict] = []
        for it in fired:
            g = it.get("group")
            if g is None:
                counted.append(it)
            elif g not in best or it["points"] > best[g]["points"]:
                best[g] = it
        counted += list(best.values())
        raw = sum(it["points"] for it in counted)
        score = min(raw, dom["cap"])
        domain_scores[dkey] = {"label": dom["label"], "score": score, "raw": raw, "cap": dom["cap"], "capped": raw > dom["cap"]}
        total += score
        max_total += dom["cap"]
        for it in counted:
            drivers.append(Driver(kind="clinical", id=it["id"], label=it["label"], evidence=it["evidence"],
                                  effect=f"+{it['points']} (domain {dkey}: {dom['label']})",
                                  scope="eye" if it["fact"] in per_eye_facts else "patient", eye=eye,
                                  value=ctx[it["fact"]], points=it["points"]))
    return domain_scores, drivers, total, max_total


def _red_flag_fires(rf: dict, eye_ctx: dict[str, dict], patient_ctx: dict, eye: str) -> bool:
    if rf["scope"] == "eye":
        c = eye_ctx[eye]
        return _all([_cond(c[x["fact"]], x["op"], x.get("value")) for x in rf["all"]]) is True
    parts: list[bool | None] = [_cond(patient_ctx[x["fact"]], x["op"], x.get("value")) for x in rf.get("all", [])]
    if rf.get("any_eye"):
        parts.append(_any([_cond(eye_ctx[e][x["fact"]], x["op"], x.get("value")) for e in EYES for x in rf["any_eye"]]))
    return _all(parts) is True


def _clinical_band(score: int, flags: list[str], rules: RiskRules) -> str:
    b = rules.data["clinical"]["bands"]
    if flags or score >= b["C2_min_score"]:
        return "C2"
    return "C1" if score >= b["C1_min_score"] else "C0"


# --------------------------------------------------------------------------- public API

def assess_risk(clinical: ClinicalInput | None, eyes: Mapping[str, EyeImageInput | None], *,
                age_years: int | None, rules: RiskRules | None = None) -> RiskAssessment:
    """Combine per-eye ConvNeXt output with clinical factors. Pure and deterministic; inputs are never modified.

    eyes: {"right": EyeImageInput | None, "left": EyeImageInput | None}; None (or a missing key) = no image for that eye.
    """
    rules = rules or default_rules()
    data = rules.data
    rank = {t: i for i, t in enumerate(data["tiers"])}
    matrix, ovr = data["combination"]["matrix"], data["combination"]["overrides"]
    c = clinical if clinical is not None else ClinicalInput()
    src = _sources(c, age_years, rules)
    patient_ctx = _patient_facts(src, rules)
    eye_ctx = {e: {**patient_ctx, **_eye_facts(src, e, rules)} for e in EYES}
    gaps, clinical_status = _data_gaps(clinical, src, rules)
    warnings: list[Note] = []
    path: list[str] = []
    results: dict[str, EyeResult] = {}

    for eye in EYES:
        name, inp = EYE_LABEL[eye], eyes.get(eye)
        reason, band = _image_eval(inp, rules)
        domain_scores, drivers, score, max_score = _score_domains(eye_ctx[eye], rules, eye)
        flags = [rf for rf in data["clinical"]["red_flags"] if _red_flag_fires(rf, eye_ctx, patient_ctx, eye)]
        for rf in flags:
            drivers.append(Driver(kind="red_flag", id=rf["id"], label=rf["label"], evidence=rf["evidence"],
                                  effect="Forces clinical band C2", scope=rf["scope"], eye=eye, value=True))
        cband = _clinical_band(score, [f["id"] for f in flags], rules)
        thr = {"thr_screening": getattr(inp, "thr_screening", None), "thr_max_f1": getattr(inp, "thr_max_f1", None)}
        common = dict(eye=eye, clinical_score=score, clinical_max_score=max_score, clinical_domain_scores=domain_scores,
                      clinical_band=cband, red_flags=[f["id"] for f in flags])

        if reason is not None:
            path.append(f"{name}: image not assessed ({_NOT_ASSESSED_TEXT[reason]}); this eye is never reported as Low.")
            path.append(f"{name}: clinical score {score}/{max_score} -> band {cband}" + (f" (red flag: {'; '.join(f['label'] for f in flags)})" if flags else "") + ".")
            results[eye] = EyeResult(state="not_assessed", not_assessed_reason=reason, drivers=drivers, **common)
            gaps.append(Note(reason, f"{name}: image not assessed - {_NOT_ASSESSED_TEXT[reason]}.", eye=eye))
            continue

        assert band is not None and inp is not None
        drivers.insert(0, Driver(kind="image", id=f"image_{band}", label=data["image"]["bands"][band], evidence=data["image"]["evidence"][band],
                                 effect=f"Image band {band}", eye=eye, value=round(inp.risk_prob, 5)))
        path.append(f"{name}: image risk score {inp.risk_prob:.3f} -> band {band} (screening threshold {inp.thr_screening:.3f}, max-F1 threshold {inp.thr_max_f1:.3f}).")
        path.append(f"{name}: clinical score {score}/{max_score} -> band {cband}" + (f" (red flag: {'; '.join(f['label'] for f in flags)})" if flags else "") + ".")
        tier = matrix[band][cband]
        matrix_tier, overrides = tier, []
        drivers.append(Driver(kind="combination", id=f"matrix_{band}_{cband}", label=f"Combination matrix: image {band} + clinical {cband}",
                              evidence=data["combination"]["evidence"], effect=f"Tier {tier}", eye=eye, value=tier))
        path.append(f"{name}: matrix(image {band}, clinical {cband}) = {tier}.")
        if inp.needs_review and rank[tier] < rank[ovr["model_needs_review_min_tier"]]:
            tier = ovr["model_needs_review_min_tier"]
            overrides.append("model_needs_review_floor")
            drivers.append(Driver(kind="override", id="model_needs_review_floor", label="Model flagged this image as uncertain (needs_review)",
                                  evidence=data["combination"]["evidence"], effect=f"Tier raised to at least {tier}", eye=eye, value=True))
            path.append(f"{name}: model uncertain (needs_review) -> tier raised to at least {tier}.")
        if inp.needs_review:
            warnings.append(Note("model_uncertain", f"{name}: the model's confidence is low for this image (needs_review).", eye=eye))
        if inp.quality_status == "warn":
            codes = ", ".join(inp.quality_issue_codes) or "see quality report"
            warnings.append(Note("quality_warning", f"{name}: image-quality warning ({codes}). The quality check is an unvalidated heuristic; tier not changed.", eye=eye))
        for w in inp.model_warnings:
            warnings.append(Note("model_warning", f"{name}: {w}", eye=eye))
        results[eye] = EyeResult(state="assessed", image_band=band, risk_prob=round(inp.risk_prob, 5), needs_review=bool(inp.needs_review),
                                 matrix_tier=matrix_tier, tier=tier, overrides_applied=overrides, drivers=drivers, **thr, **common)

    assessed = [e for e in EYES if results[e].state == "assessed"]
    patient_drivers: list[Driver] = []
    if not assessed:
        tier, driven = INCOMPLETE, None
        path.append("No eye has a usable image, so no Low / Moderate / High tier can be assigned (Incomplete). Clinical bands are shown for information only.")
    else:
        driven = max(assessed, key=lambda e: (rank[results[e].tier], -EYES.index(e)))
        tier = results[driven].tier
        path.append(f"Patient tier = worst assessed eye ({EYE_LABEL[driven]}) = {tier}.")
        floor = ovr["unassessed_eye_clinical_c2_min_tier"]
        for e in EYES:
            r = results[e]
            if r.state == "not_assessed" and r.clinical_band == "C2" and rank[tier] < rank[floor]:
                tier = floor
                patient_drivers.append(Driver(kind="override", id="unassessed_eye_clinical_c2_floor", scope="patient", eye=e, value=True,
                                              label=f"{EYE_LABEL[e]} has no usable image but its clinical band is C2",
                                              evidence=data["combination"]["evidence"], effect=f"Patient tier raised to at least {floor}"))
                path.append(f"{EYE_LABEL[e]} could not be assessed and its clinical band is C2 -> patient tier raised to at least {floor}.")
        if tier == data["tiers"][0] and clinical_status != "complete":
            warnings.append(Note("low_with_incomplete_clinical", "Low was computed without complete clinical data; treat it as image-based only."))
        missing_eyes = [e for e in EYES if results[e].state == "not_assessed"]
        if tier == data["tiers"][0] and missing_eyes:
            warnings.append(Note("low_with_unassessed_eye", f"Low rests on one eye only; {', '.join(EYE_LABEL[e] for e in missing_eyes)} could not be assessed."))
    return RiskAssessment(rules_version=rules.version, rules_sha256=rules.sha256, tier=tier, tier_driven_by=driven,
                          clinical_status=clinical_status, eyes=results, patient_drivers=patient_drivers,
                          decision_path=path, data_gaps=gaps, warnings=warnings,
                          rules_status=data["status"], evidence_legend=dict(data["evidence_legend"]))
