"""Install the exported model from the research bundle into models/<tag>/ and verify it.

    python -m scripts.install_model --bundle /path/to/bundle_convnext_tiny_v1.zip

Copies model/* verbatim (fundus_inference.py is NOT modified) and docs/MODEL_CARD.md into docs/.
Aborts if model_weights.pt does not match the SHA-256 in export_manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--dest", type=Path, default=ROOT / "models" / "convnext_tiny_v1")
    args = ap.parse_args()

    with zipfile.ZipFile(args.bundle) as z:
        model_files = [n for n in z.namelist() if n.startswith("model/") and not n.endswith("/")]
        if "model/model_weights.pt" not in model_files or "model/export_manifest.json" not in model_files:
            print("Bundle does not contain model/model_weights.pt and model/export_manifest.json", file=sys.stderr)
            return 1
        args.dest.mkdir(parents=True, exist_ok=True)
        for name in model_files:
            target = args.dest / Path(name).name          # flat names only: no path traversal possible
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            print(f"  extracted {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
        if "docs/MODEL_CARD.md" in z.namelist():
            (ROOT / "docs").mkdir(exist_ok=True)
            with z.open("docs/MODEL_CARD.md") as src, open(ROOT / "docs" / "MODEL_CARD.md", "wb") as out:
                shutil.copyfileobj(src, out)
            print("  extracted docs/MODEL_CARD.md")

    expected = json.loads((args.dest / "export_manifest.json").read_text())["weights_sha256"]
    h = hashlib.sha256()
    with open(args.dest / "model_weights.pt", "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        print(f"SHA-256 MISMATCH: expected {expected}, got {h.hexdigest()}", file=sys.stderr)
        return 2
    print(f"OK: weights verified ({expected[:16]}…) -> {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
