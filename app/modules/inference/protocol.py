# """Model-facing contracts. Anything that turns an image file into a FundusPrediction can replace the
# ConvNeXt engine without touching routers/DB code. A future multimodal (image + clinical) model would
# get its own protocol keyed on a screening, not on a single image - see docs/EXTENDING.md."""
# from __future__ import annotations

# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Protocol

# import numpy as np

# RESEARCH_NOTICE = ("Research prototype. Not a medical device and not clinically validated; not for diagnosis or patient care. "
#                    "Outputs support, and never replace, review by a qualified clinician.")


# @dataclass(frozen=True)
# class FundusPrediction:
#     risk_prob: float
#     risk_abnormal_maxf1: bool
#     risk_abnormal_screening: bool
#     risk_confidence: float
#     needs_review: bool
#     flagged_diseases: list[str]
#     disease_probs: dict[str, float]
#     crop_ok: bool
#     warnings: list[str]
#     embedding: np.ndarray            # float32, shape (embedding_dim,)
#     inference_ms: int = 0


# @dataclass(frozen=True)
# class ModelInfo:
#     tag: str
#     weights_sha256: str
#     meta: dict = field(default_factory=dict)  # snapshot stored with every prediction

#     @property
#     def core_classes(self) -> list[str]:
#         return list(self.meta.get("core_classes", []))


# class ImageModel(Protocol):
#     info: ModelInfo
#     disease_names: dict[str, str]

#     def predict_one(self, image_path: Path) -> FundusPrediction: ...


"""Model-facing contracts. Anything that turns an image file into a FundusPrediction can replace the
ConvNeXt engine without touching routers/DB code. A future multimodal (image + clinical) model would
get its own protocol keyed on a screening, not on a single image - see docs/EXTENDING.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

RESEARCH_NOTICE = ("Research prototype. Not a medical device and not clinically validated; not for diagnosis or patient care. "
                   "Outputs support, and never replace, review by a qualified clinician.")


@dataclass(frozen=True)
class FundusPrediction:
    risk_prob: float
    risk_abnormal_maxf1: bool
    risk_abnormal_screening: bool
    risk_confidence: float
    needs_review: bool
    flagged_diseases: list[str]
    disease_probs: dict[str, float]
    crop_ok: bool
    warnings: list[str]
    embedding: np.ndarray            # float32, shape (embedding_dim,)
    inference_ms: int = 0


RISK_TARGET = "risk"   # Grad-CAM target meaning the Disease_Risk (abnormal vs normal) output

GRADCAM_NOTICE = ("Grad-CAM shows which image regions most increased the model's score for the selected output. It is coarse "
                  "(12x12 grid), is not a lesion detector, and its localisation has not been validated against annotations. "
                  "Never use it as evidence of a finding or to replace clinical examination.")


@dataclass(frozen=True)
class GradCamResult:
    target: str            # RISK_TARGET or an RFMiD code
    overlay_jpeg: bytes    # heatmap blended onto the model's input view (cropped, squared fundus), not the raw upload
    resolution: int        # side length in pixels of the overlay
    grid_size: int         # side of the native Grad-CAM grid (e.g. 12)
    empty: bool            # True when every positive contribution was zero -> nothing meaningful to show
    inference_ms: int = 0


@dataclass(frozen=True)
class ModelInfo:
    tag: str
    weights_sha256: str
    meta: dict = field(default_factory=dict)  # snapshot stored with every prediction

    @property
    def core_classes(self) -> list[str]:
        return list(self.meta.get("core_classes", []))


class ImageModel(Protocol):
    info: ModelInfo
    disease_names: dict[str, str]

    def predict_one(self, image_path: Path) -> FundusPrediction: ...


@runtime_checkable
class Explainer(Protocol):
    """Optional capability. Engines that can explain a prediction implement this in addition to ImageModel."""

    def explain_one(self, image_path: Path, target: str) -> GradCamResult: ...
