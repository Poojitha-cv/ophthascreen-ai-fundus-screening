# """Score images with the model OUTSIDE the web app, to separate 'the app changed' from 'the images differ'.

#     python -m scripts.check_image img1.jpg img2.png ... [--save-view out_dir]

# Prints, per file: Disease_Risk probability, the two thresholds, confidence, needs_review, crop_ok and the top classes.
# --save-view writes the exact 512 px square the model sees (after its border crop) so you can look at it.
# The same file always gives the same numbers. If this script and the app disagree for one file, there is an app bug;
# if they agree, the difference is in the images (camera, colour, borders, glare), not in the code.
# """
# from __future__ import annotations

# import argparse
# import sys
# from pathlib import Path

# from PIL import Image

# from app.core.config import Settings
# from app.modules.inference.engine import FundusEngine


# def main() -> int:
#     ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#     ap.add_argument("files", nargs="+", type=Path)
#     ap.add_argument("--save-view", type=Path, default=None)
#     a = ap.parse_args()
#     eng = FundusEngine(Settings().model_dir)
#     m = eng.info.meta
#     print(f"model {eng.info.tag}  screening>={m['risk_thr_sens95']:.3f}  max-F1>={m['risk_thr_maxF1']:.3f}\n")
#     if a.save_view:
#         a.save_view.mkdir(parents=True, exist_ok=True)
#     for f in a.files:
#         p = eng.predict_one(f)
#         top = sorted(((c, p.disease_probs[c]) for c in m["core_classes"]), key=lambda t: -t[1])[:3]
#         band = "above max-F1" if p.risk_abnormal_maxf1 else "above screening" if p.risk_abnormal_screening else "below screening"
#         with Image.open(f) as im:
#             size = im.size
#         print(f"{f.name}  {size[0]}x{size[1]}\n  risk {p.risk_prob:.4f} ({band})  confidence {p.risk_confidence:.2f}  "
#               f"needs_review {p.needs_review}  crop_ok {p.crop_ok}\n  top: " + ", ".join(f"{c} {v:.3f}" for c, v in top))
#         for w in p.warnings:
#             print("  warning:", w)
#         if a.save_view:
#             arr, _ = eng._screener.preprocess(str(f))
#             Image.fromarray(arr).save(a.save_view / f"{f.stem}_model_view.png")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())


"""Score images with the model OUTSIDE the web app, to separate 'the app changed' from 'the images differ'.

    python -m scripts.check_image img1.jpg folder_of_images ... [--save-view out_dir] [--csv results.csv] [--limit N]

Per file: Disease_Risk probability, confidence, needs_review, crop_ok and the top classes. Folders are scanned for
jpg/png. With more than one image it ends with a summary: how many fall above the screening / max-F1 cut-offs and how
many are 'uncertain'. On a folder of images you know are normal, 'above screening' is your false-positive rate on that
dataset; compare it with RFMiD validation specificity at the screening cut-off (0.888 -> about 11% flagged).
--save-view writes the exact 512 px square the model sees (after its border crop).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.modules.inference.engine import FundusEngine

EXT = {".jpg", ".jpeg", ".png"}


def collect(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        out += sorted(f for f in p.rglob("*") if f.suffix.lower() in EXT) if p.is_dir() else [p]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--save-view", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    a = ap.parse_args()
    files = collect(a.files)[: a.limit or None]
    eng = FundusEngine(Settings().model_dir)
    m = eng.info.meta
    print(f"model {eng.info.tag}  screening>={m['risk_thr_sens95']:.3f}  max-F1>={m['risk_thr_maxF1']:.3f}  images: {len(files)}\n")
    if a.save_view:
        a.save_view.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in files:
        p = eng.predict_one(f)
        top = sorted(((c, p.disease_probs[c]) for c in m["core_classes"]), key=lambda t: -t[1])[:3]
        band = "above max-F1" if p.risk_abnormal_maxf1 else "above screening" if p.risk_abnormal_screening else "below screening"
        with Image.open(f) as im:
            size = im.size
        rows.append({"file": f.name, "width": size[0], "height": size[1], "risk": round(p.risk_prob, 4), "band": band,
                     "confidence": round(p.risk_confidence, 2), "needs_review": p.needs_review, "crop_ok": p.crop_ok,
                     "top1": f"{top[0][0]} {top[0][1]:.3f}"})
        if len(files) <= 20:
            print(f"{f.name}  {size[0]}x{size[1]}\n  risk {p.risk_prob:.4f} ({band})  confidence {p.risk_confidence:.2f}  "
                  f"needs_review {p.needs_review}  crop_ok {p.crop_ok}\n  top: " + ", ".join(f"{c} {v:.3f}" for c, v in top))
            for w in p.warnings:
                print("  warning:", w)
        if a.save_view:
            arr, _ = eng._screener.preprocess(str(f))
            Image.fromarray(arr).save(a.save_view / f"{f.stem}_model_view.png")
    if a.csv and rows:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {a.csv}")
    if len(rows) > 1:
        n = len(rows)
        scr = sum(r["band"] != "below screening" for r in rows)
        mf1 = sum(r["band"] == "above max-F1" for r in rows)
        unc = sum(bool(r["needs_review"]) for r in rows)
        bad = sum(not r["crop_ok"] for r in rows)
        print(f"\nSUMMARY over {n} images")
        print(f"  above screening cut-off : {scr} ({scr / n:.1%})")
        print(f"  above max-F1 cut-off    : {mf1} ({mf1 / n:.1%})")
        print(f"  model uncertain         : {unc} ({unc / n:.1%})   (RFMiD validation: 20% by definition)")
        print(f"  border crop failed      : {bad} ({bad / n:.1%})")
        print("  If these are all NORMAL images, 'above screening' is the false-positive rate on this dataset.")
        print("  RFMiD validation specificity at the screening cut-off was 0.888 (about 11% flagged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())