"""Fundus image quality assessment (classical image statistics, no learned model).

IMPORTANT: this is a heuristic screen, not a validated gradeability classifier. It exists to catch
obviously unusable uploads (wrong file, black/empty frame, tiny image) and to surface *warnings* a
doctor can weigh. Thresholds live in settings (QualityThresholds) and must be calibrated on real
images from your cameras - see scripts/quality_stats.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image

from app.core.config import QualityThresholds

QUALITY_CHECKER_VERSION = "heuristic-v1"

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass
class Issue:
    code: str
    severity: str  # warn | fail
    message: str


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    m = mask
    for _ in range(r):
        p = np.pad(m, 1, constant_values=False)
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def _status(issues: list[Issue]) -> str:
    if any(i.severity == FAIL for i in issues):
        return FAIL
    return WARN if issues else PASS


def finalize(report: dict) -> dict:
    """Recompute status after extra issues were appended (e.g. duplicate-upload warnings)."""
    issues = [Issue(**i) for i in report["issues"]]
    report["status"] = _status(issues)
    return report


def assess_quality(img: Image.Image, t: QualityThresholds) -> dict:
    """Returns a JSON-serialisable report: {status, checker_version, issues[], metrics{}}."""
    w, h = img.size
    issues: list[Issue] = []
    metrics: dict = {"width": w, "height": h}

    if min(w, h) < t.min_side_px:
        issues.append(Issue("too_small", FAIL, f"Image is {w}x{h}px; shorter side must be at least {t.min_side_px}px."))

    work = img.convert("RGB")
    if max(w, h) > t.work_size:
        work = work.copy()
        work.thumbnail((t.work_size, t.work_size), Image.Resampling.LANCZOS, reducing_gap=3.0)
    arr = np.asarray(work, dtype=np.float32)

    mask = arr.max(axis=2) > t.bg_threshold
    rows = mask.sum(axis=1) >= 3
    cols = mask.sum(axis=0) >= 3
    fov_fraction = float(mask.mean())
    metrics["fov_fraction"] = round(fov_fraction, 4)

    if not rows.any() or not cols.any() or fov_fraction < t.min_fov_fraction_fail:
        issues.append(Issue("no_fundus_region", FAIL, "No fundus region found (image is empty/black or the retina fills too little of the frame)."))
        return _report(issues, metrics)

    ys, xs = np.where(rows)[0], np.where(cols)[0]
    bw, bh = xs[-1] - xs[0] + 1, ys[-1] - ys[0] + 1
    aspect = float(bw / bh)
    metrics["fov_aspect"] = round(aspect, 3)
    lo, hi = t.fov_aspect_range
    if not lo <= aspect <= hi:
        issues.append(Issue("fundus_field_cut_off", WARN, "Fundus field is not roughly circular; it may be cropped or partly outside the frame."))

    px = arr[mask]
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    lum = float((0.299 * r + 0.587 * g + 0.114 * b).mean())
    contrast = float(g.std())
    saturated = float((px.max(axis=1) >= 250).mean())
    rg = float(r.mean() / max(g.mean(), 1.0))
    metrics.update(mean_luminance=round(lum, 2), green_contrast_std=round(contrast, 2),
                   saturated_fraction=round(saturated, 4), red_green_ratio=round(rg, 3))

    if lum < t.dark_mean_fail:
        issues.append(Issue("too_dark", FAIL, "Image is almost black inside the fundus region."))
    elif lum < t.dark_mean_warn:
        issues.append(Issue("dark", WARN, "Image is dark; retinal detail may be lost."))
    if lum > t.bright_mean_warn:
        issues.append(Issue("overexposed", WARN, "Image is very bright; may be overexposed."))
    if saturated > t.saturated_fraction_warn:
        issues.append(Issue("saturated_pixels", WARN, "A large part of the fundus is saturated (clipped highlights)."))
    if contrast < t.contrast_std_warn:
        issues.append(Issue("low_contrast", WARN, "Low contrast inside the fundus region."))
    if rg < t.red_green_ratio_warn:
        issues.append(Issue("unusual_colour_profile", WARN, "Colour profile is not red-dominant; this may not be a colour fundus photograph."))

    inner = _erode(mask, t.erosion_px)[1:-1, 1:-1]
    if inner.sum() >= 1000:
        gch = arr[..., 1]
        lap = -4 * gch[1:-1, 1:-1] + gch[:-2, 1:-1] + gch[2:, 1:-1] + gch[1:-1, :-2] + gch[1:-1, 2:]
        sharp = float(lap[inner].var())
        metrics["sharpness_lapvar"] = round(sharp, 3)
        if sharp < t.blur_lapvar_warn:
            issues.append(Issue("blurry", WARN, "Image appears blurry / out of focus."))
    else:
        metrics["sharpness_lapvar"] = None

    return _report(issues, metrics)


def _report(issues: list[Issue], metrics: dict) -> dict:
    return {"status": _status(issues), "checker_version": QUALITY_CHECKER_VERSION,
            "issues": [asdict(i) for i in issues], "metrics": metrics}
