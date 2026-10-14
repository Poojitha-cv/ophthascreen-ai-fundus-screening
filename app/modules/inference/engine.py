# # """Wraps the exported ConvNeXt-Tiny bundle (models/<tag>/fundus_inference.py) WITHOUT modifying it.

# # * Verifies model_weights.pt against export_manifest.json (SHA-256) before loading.
# # * Loads once at startup; inference is serialised with a lock (one shared torch model).
# # * Records the thresholds/temperature in effect so stored predictions stay interpretable even if
# #   the model is later replaced.
# # """
# # from __future__ import annotations

# # import hashlib
# # import importlib.util
# # import json
# # import logging
# # import threading
# # import time
# # from pathlib import Path

# # import numpy as np

# # from app.core.config import Settings
# # from app.modules.inference.protocol import FundusPrediction, ModelInfo

# # log = logging.getLogger(__name__)

# # _REQUIRED = ("fundus_inference.py", "inference_config.json", "export_manifest.json", "model_weights.pt")


# # class ModelLoadError(RuntimeError):
# #     pass


# # def _sha256(path: Path) -> str:
# #     h = hashlib.sha256()
# #     with open(path, "rb") as f:
# #         for chunk in iter(lambda: f.read(1 << 20), b""):
# #             h.update(chunk)
# #     return h.hexdigest()


# # class FundusEngine:
# #     def __init__(self, model_dir: Path, device: str | None = None):
# #         model_dir = Path(model_dir)
# #         missing = [n for n in _REQUIRED if not (model_dir / n).is_file()]
# #         if missing:
# #             raise ModelLoadError(f"{model_dir}: missing {missing}. Run scripts/install_model.py --bundle <bundle.zip>")

# #         manifest = json.loads((model_dir / "export_manifest.json").read_text())
# #         cfg = json.loads((model_dir / "inference_config.json").read_text())
# #         actual = _sha256(model_dir / "model_weights.pt")
# #         if actual != manifest["weights_sha256"]:
# #             raise ModelLoadError(f"model_weights.pt SHA-256 mismatch (expected {manifest['weights_sha256']}, got {actual})")

# #         spec = importlib.util.spec_from_file_location("fundus_inference", model_dir / "fundus_inference.py")
# #         module = importlib.util.module_from_spec(spec)
# #         spec.loader.exec_module(module)
# #         self._screener = module.FundusScreener(str(model_dir), device=device)
# #         self._lock = threading.Lock()

# #         import torch
# #         names_file = model_dir / "disease_names.json"  # optional, user-supplied (not shipped: names must come from the dataset paper)
# #         self.disease_names: dict[str, str] = json.loads(names_file.read_text()) if names_file.is_file() else {}
# #         self.info = ModelInfo(
# #             tag=manifest["tag"], weights_sha256=actual,
# #             meta={
# #                 "tag": manifest["tag"], "backbone": cfg["model_name"], "checkpoint_epoch": cfg.get("checkpoint_epoch"),
# #                 "temperature": cfg["temperature"], "risk_thr_maxF1": cfg["risk_thr_maxF1"], "risk_thr_sens95": cfg["risk_thr_sens95"],
# #                 "review_confidence_cutoff": cfg["review_confidence_cutoff"], "core_classes": cfg["core_classes"],
# #                 "disease_thr_global": cfg["disease_thr_global"], "disease_thr_per_class": cfg["disease_thr_per_class"],
# #                 "embedding_dim": cfg["embedding_dim"], "runtime_torch": torch.__version__, "device": str(self._screener.device),
# #             })
# #         log.info("Loaded model %s (sha256 %s…) on %s", self.info.tag, actual[:12], self._screener.device)

# #     def predict_one(self, image_path: Path) -> FundusPrediction:
# #         t0 = time.perf_counter()
# #         with self._lock:
# #             out = self._screener.predict([str(image_path)], return_embedding=True)[0]
# #         return FundusPrediction(
# #             risk_prob=out["risk_prob"], risk_abnormal_maxf1=bool(out["risk_abnormal_maxF1"]),
# #             risk_abnormal_screening=bool(out["risk_abnormal_screening"]), risk_confidence=out["risk_confidence"],
# #             needs_review=bool(out["needs_review"]), flagged_diseases=list(out["flagged_diseases"]),
# #             disease_probs=dict(out["disease_probs"]), crop_ok=bool(out["crop_ok"]), warnings=list(out["warnings"]),
# #             embedding=np.asarray(out["embedding"], dtype=np.float32), inference_ms=int((time.perf_counter() - t0) * 1000))


# # def load_engine(settings: Settings) -> FundusEngine | None:
# #     """Returns the engine, or None when unavailable (uploads are then stored as 'pending' and can be
# #     analysed later). With OPH_REQUIRE_MODEL=true a load failure aborts startup instead."""
# #     try:
# #         return FundusEngine(settings.model_dir, settings.model_device)
# #     except Exception as exc:
# #         if settings.require_model:
# #             raise
# #         log.error("Model NOT loaded (%s: %s). Uploads will be stored without AI analysis.", type(exc).__name__, exc)
# #         return None


# """Wraps the exported ConvNeXt-Tiny bundle (models/<tag>/fundus_inference.py) WITHOUT modifying it.

# * Verifies model_weights.pt against export_manifest.json (SHA-256) before loading.
# * Loads once at startup; inference is serialised with a lock (one shared torch model).
# * Records the thresholds/temperature in effect so stored predictions stay interpretable even if
#   the model is later replaced.
# """
# from __future__ import annotations

# import hashlib
# import importlib.util
# import json
# import logging
# import threading
# import time
# from pathlib import Path

# import numpy as np

# from app.core.config import Settings
# from app.modules.inference.protocol import FundusPrediction, ModelInfo
# from app.modules.inference.rfmid_labels import RFMID_NAMES

# log = logging.getLogger(__name__)

# _REQUIRED = ("fundus_inference.py", "inference_config.json", "export_manifest.json", "model_weights.pt")


# class ModelLoadError(RuntimeError):
#     pass


# def _sha256(path: Path) -> str:
#     h = hashlib.sha256()
#     with open(path, "rb") as f:
#         for chunk in iter(lambda: f.read(1 << 20), b""):
#             h.update(chunk)
#     return h.hexdigest()


# class FundusEngine:
#     def __init__(self, model_dir: Path, device: str | None = None):
#         model_dir = Path(model_dir)
#         missing = [n for n in _REQUIRED if not (model_dir / n).is_file()]
#         if missing:
#             raise ModelLoadError(f"{model_dir}: missing {missing}. Run scripts/install_model.py --bundle <bundle.zip>")

#         manifest = json.loads((model_dir / "export_manifest.json").read_text())
#         cfg = json.loads((model_dir / "inference_config.json").read_text())
#         actual = _sha256(model_dir / "model_weights.pt")
#         if actual != manifest["weights_sha256"]:
#             raise ModelLoadError(f"model_weights.pt SHA-256 mismatch (expected {manifest['weights_sha256']}, got {actual})")

#         spec = importlib.util.spec_from_file_location("fundus_inference", model_dir / "fundus_inference.py")
#         module = importlib.util.module_from_spec(spec)
#         spec.loader.exec_module(module)
#         self._screener = module.FundusScreener(str(model_dir), device=device)
#         self._lock = threading.Lock()

#         import torch
#         # Full RFMiD names for the model's own disease columns (codes verified against the dataset CSV header).
#         unknown = [c for c in cfg["disease_cols"] if c not in RFMID_NAMES]
#         if unknown:
#             log.warning("No RFMiD name for model output(s) %s; they will be shown by code only.", unknown)
#         self.disease_names: dict[str, str] = {c: RFMID_NAMES[c] for c in cfg["disease_cols"] if c in RFMID_NAMES}
#         self.info = ModelInfo(
#             tag=manifest["tag"], weights_sha256=actual,
#             meta={
#                 "tag": manifest["tag"], "backbone": cfg["model_name"], "checkpoint_epoch": cfg.get("checkpoint_epoch"),
#                 "temperature": cfg["temperature"], "risk_thr_maxF1": cfg["risk_thr_maxF1"], "risk_thr_sens95": cfg["risk_thr_sens95"],
#                 "review_confidence_cutoff": cfg["review_confidence_cutoff"], "core_classes": cfg["core_classes"],
#                 "disease_thr_global": cfg["disease_thr_global"], "disease_thr_per_class": cfg["disease_thr_per_class"],
#                 "embedding_dim": cfg["embedding_dim"], "runtime_torch": torch.__version__, "device": str(self._screener.device),
#             })
#         log.info("Loaded model %s (sha256 %s…) on %s", self.info.tag, actual[:12], self._screener.device)

#     def predict_one(self, image_path: Path) -> FundusPrediction:
#         t0 = time.perf_counter()
#         with self._lock:
#             out = self._screener.predict([str(image_path)], return_embedding=True)[0]
#         return FundusPrediction(
#             risk_prob=out["risk_prob"], risk_abnormal_maxf1=bool(out["risk_abnormal_maxF1"]),
#             risk_abnormal_screening=bool(out["risk_abnormal_screening"]), risk_confidence=out["risk_confidence"],
#             needs_review=bool(out["needs_review"]), flagged_diseases=list(out["flagged_diseases"]),
#             disease_probs=dict(out["disease_probs"]), crop_ok=bool(out["crop_ok"]), warnings=list(out["warnings"]),
#             embedding=np.asarray(out["embedding"], dtype=np.float32), inference_ms=int((time.perf_counter() - t0) * 1000))


# def load_engine(settings: Settings) -> FundusEngine | None:
#     """Returns the engine, or None when unavailable (uploads are then stored as 'pending' and can be
#     analysed later). With OPH_REQUIRE_MODEL=true a load failure aborts startup instead."""
#     try:
#         return FundusEngine(settings.model_dir, settings.model_device)
#     except Exception as exc:
#         if settings.require_model:
#             raise
#         log.error("Model NOT loaded (%s: %s). Uploads will be stored without AI analysis.", type(exc).__name__, exc)
#         return None




"""Wraps the exported ConvNeXt-Tiny bundle (models/<tag>/fundus_inference.py) WITHOUT modifying it.

* Verifies model_weights.pt against export_manifest.json (SHA-256) before loading.
* Loads once at startup; inference is serialised with a lock (one shared torch model).
* Records the thresholds/temperature in effect so stored predictions stay interpretable even if
  the model is later replaced.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from app.core.config import Settings
from app.modules.inference.protocol import RISK_TARGET, FundusPrediction, GradCamResult, ModelInfo
from app.modules.inference.rfmid_labels import RFMID_NAMES

log = logging.getLogger(__name__)

_REQUIRED = ("fundus_inference.py", "inference_config.json", "export_manifest.json", "model_weights.pt")


class ModelLoadError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FundusEngine:
    def __init__(self, model_dir: Path, device: str | None = None, cam_cache_items: int = 64):
        model_dir = Path(model_dir)
        missing = [n for n in _REQUIRED if not (model_dir / n).is_file()]
        if missing:
            raise ModelLoadError(f"{model_dir}: missing {missing}. Run scripts/install_model.py --bundle <bundle.zip>")

        manifest = json.loads((model_dir / "export_manifest.json").read_text())
        cfg = json.loads((model_dir / "inference_config.json").read_text())
        actual = _sha256(model_dir / "model_weights.pt")
        if actual != manifest["weights_sha256"]:
            raise ModelLoadError(f"model_weights.pt SHA-256 mismatch (expected {manifest['weights_sha256']}, got {actual})")

        spec = importlib.util.spec_from_file_location("fundus_inference", model_dir / "fundus_inference.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._screener = module.FundusScreener(str(model_dir), device=device)
        self._lock = threading.Lock()
        self._cam_cache: OrderedDict[tuple[str, str], GradCamResult] = OrderedDict()  # in memory only: derived from PHI, never persisted
        self._cam_cache_items = max(0, cam_cache_items)

        import torch
        # Full RFMiD names for the model's own disease columns (codes verified against the dataset CSV header).
        unknown = [c for c in cfg["disease_cols"] if c not in RFMID_NAMES]
        if unknown:
            log.warning("No RFMiD name for model output(s) %s; they will be shown by code only.", unknown)
        self.disease_names: dict[str, str] = {c: RFMID_NAMES[c] for c in cfg["disease_cols"] if c in RFMID_NAMES}
        self.info = ModelInfo(
            tag=manifest["tag"], weights_sha256=actual,
            meta={
                "tag": manifest["tag"], "backbone": cfg["model_name"], "checkpoint_epoch": cfg.get("checkpoint_epoch"),
                "temperature": cfg["temperature"], "risk_thr_maxF1": cfg["risk_thr_maxF1"], "risk_thr_sens95": cfg["risk_thr_sens95"],
                "review_confidence_cutoff": cfg["review_confidence_cutoff"], "core_classes": cfg["core_classes"],
                "disease_thr_global": cfg["disease_thr_global"], "disease_thr_per_class": cfg["disease_thr_per_class"],
                "embedding_dim": cfg["embedding_dim"], "runtime_torch": torch.__version__, "device": str(self._screener.device),
            })
        log.info("Loaded model %s (sha256 %s…) on %s", self.info.tag, actual[:12], self._screener.device)

    def predict_one(self, image_path: Path) -> FundusPrediction:
        t0 = time.perf_counter()
        with self._lock:
            out = self._screener.predict([str(image_path)], return_embedding=True)[0]
        return FundusPrediction(
            risk_prob=out["risk_prob"], risk_abnormal_maxf1=bool(out["risk_abnormal_maxF1"]),
            risk_abnormal_screening=bool(out["risk_abnormal_screening"]), risk_confidence=out["risk_confidence"],
            needs_review=bool(out["needs_review"]), flagged_diseases=list(out["flagged_diseases"]),
            disease_probs=dict(out["disease_probs"]), crop_ok=bool(out["crop_ok"]), warnings=list(out["warnings"]),
            embedding=np.asarray(out["embedding"], dtype=np.float32), inference_ms=int((time.perf_counter() - t0) * 1000))


    def explain_one(self, image_path: Path, target: str) -> GradCamResult:
        """Grad-CAM for one stored image. target = 'risk' (Disease_Risk) or a validated (core) RFMiD class.

        Same lock as predict_one (the hook is placed on the one shared model). Results are cached per (file, target); the cache
        lives inside this engine instance, so installing different weights (new engine) can never serve a stale map."""
        if target != RISK_TARGET and target not in self.info.core_classes:
            raise ValueError(f"Grad-CAM is only offered for 'risk' and validated classes; got {target!r}")
        key = (str(image_path), target)
        with self._lock:
            hit = self._cam_cache.get(key)
            if hit is not None:
                self._cam_cache.move_to_end(key)
                return hit
            from app.modules.inference import explain as gradcam   # lazy: keeps torch out of module import (app still boots without it)
            res = gradcam.explain(self._screener, image_path, target)
            if self._cam_cache_items:
                self._cam_cache[key] = res
                while len(self._cam_cache) > self._cam_cache_items:
                    self._cam_cache.popitem(last=False)
            return res


def load_engine(settings: Settings) -> FundusEngine | None:
    """Returns the engine, or None when unavailable (uploads are then stored as 'pending' and can be
    analysed later). With OPH_REQUIRE_MODEL=true a load failure aborts startup instead."""
    try:
        return FundusEngine(settings.model_dir, settings.model_device, settings.gradcam_cache_items)
    except Exception as exc:
        if settings.require_model:
            raise
        log.error("Model NOT loaded (%s: %s). Uploads will be stored without AI analysis.", type(exc).__name__, exc)
        return None
