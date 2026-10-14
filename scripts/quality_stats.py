"""Measure the quality-check metrics over a folder of REAL fundus images, to calibrate thresholds.

    python -m scripts.quality_stats --dir /path/to/images --out quality_metrics.csv [--limit 500]

Prints percentiles for every metric and how many images each current threshold would flag. Use it on
images from your own cameras (e.g. a sample of the RFMiD training data, plus images you know are bad),
then set OPH_QUALITY__* values accordingly. The defaults in app/core/config.py are NOT calibrated.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.config import QualityThresholds
from app.modules.imaging.quality import assess_quality

METRICS = ["fov_fraction", "fov_aspect", "mean_luminance", "green_contrast_std", "saturated_fraction", "red_green_ratio", "sharpness_lapvar"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("quality_metrics.csv"))
    ap.add_argument("--limit", type=int, default=0, help="0 = all images")
    args = ap.parse_args()

    files = sorted(p for p in args.dir.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("No images found", file=sys.stderr)
        return 1

    t = QualityThresholds()
    rows, issue_counts, status_counts = [], Counter(), Counter()
    for i, p in enumerate(files, 1):
        with Image.open(p) as im:
            rep = assess_quality(im, t)
        status_counts[rep["status"]] += 1
        issue_counts.update(x["code"] for x in rep["issues"])
        rows.append({"file": str(p), "status": rep["status"], "issues": ";".join(x["code"] for x in rep["issues"]),
                     "width": rep["metrics"]["width"], "height": rep["metrics"]["height"], **{m: rep["metrics"].get(m) for m in METRICS}})
        if i % 100 == 0:
            print(f"  {i}/{len(files)}", file=sys.stderr)

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\n{len(files)} images -> {args.out}\nstatus: {dict(status_counts)}\nissues flagged by CURRENT thresholds: {dict(issue_counts)}\n")
    print(f"{'metric':22}{'p1':>10}{'p5':>10}{'p25':>10}{'p50':>10}{'p75':>10}{'p95':>10}{'p99':>10}")
    for m in METRICS:
        v = np.array([r[m] for r in rows if r[m] is not None], dtype=float)
        if len(v):
            print(f"{m:22}" + "".join(f"{np.percentile(v, q):10.3f}" for q in (1, 5, 25, 50, 75, 95, 99)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
