"""Grad-CAM for the exported ConvNeXt bundle, computed OUTSIDE the bundle.

The bundle's fundus_inference.py (hash-pinned, unmodified) runs forward-only under no_grad/fp16. Grad-CAM needs gradients,
so this module re-uses the *already loaded* FundusScreener (same weights, same preprocessing) and adds a temporary hook on the
last ConvNeXt stage for the duration of one call. Algorithm = notebook Cell 12:

    A = output of model.stages[-1]            # [1, 768, 12, 12] at 384 px input
    w = mean over space of dScore/dA          # one weight per channel
    cam = ReLU(sum_c w_c * A_c) -> bilinear upsample -> zero outside the fundus -> divide by max

The score is the raw logit (pre-temperature, pre-sigmoid) of one output. Temperature is a monotone rescale and does not change
the map's shape.
"""
from __future__ import annotations

import io
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from app.modules.inference.protocol import RISK_TARGET, GradCamResult

OVERLAY_ALPHA = 0.45   # same blend as the notebook figures
JPEG_QUALITY = 90


def target_label(target: str) -> str:
    """API target -> model output column name."""
    return "Disease_Risk" if target == RISK_TARGET else target


def jet(x: np.ndarray) -> np.ndarray:
    """matplotlib 'jet' colormap for x in [0,1] -> float RGB in [0,1] (no matplotlib dependency in the backend)."""
    r = np.clip(1.5 - np.abs(4 * x - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * x - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * x - 1), 0, 1)
    return np.stack([r, g, b], axis=-1)


def compute_cam(screener, arr: np.ndarray, output_index: int) -> tuple[np.ndarray, int, bool]:
    """arr: uint8 [S,S,3] from screener.preprocess. Returns (cam float32 [S,S] in [0,1], native grid side, empty flag).

    The caller must hold whatever lock protects the shared model."""
    model = screener.model
    stage = model.stages[-1]
    store: dict[str, torch.Tensor] = {}
    handle = stage.register_forward_hook(lambda _m, _i, out: store.__setitem__("act", out))
    try:
        was_training = model.training
        model.eval()
        x = screener._to_tensor([arr]).float().requires_grad_(True)   # identical preprocessing to predict()
        with torch.enable_grad():
            logits = model(x)                                           # fp32 on purpose: no autocast while differentiating
            act = store["act"]
            (grad,) = torch.autograd.grad(logits[0, output_index], act)  # d(score)/d(activations); no parameter .grad is touched
        if was_training:
            model.train()
    finally:
        handle.remove()                                                 # never leave a hook on the shared model
    act = act.detach()
    weights = grad.mean(dim=(2, 3), keepdim=True)
    cam = F.relu((weights * act).sum(dim=1, keepdim=True))
    grid = int(cam.shape[-1])
    cam = F.interpolate(cam, size=arr.shape[:2], mode="bilinear", align_corners=False)[0, 0]
    fundus = torch.from_numpy(arr.max(axis=2) > screener.cfg["bg_thr"]).to(cam.device)
    cam = cam * fundus
    peak = float(cam.max())
    empty = not np.isfinite(peak) or peak <= 1e-12
    if not empty:
        cam = cam / peak
    return cam.float().cpu().numpy(), grid, empty


def render_overlay(arr: np.ndarray, cam: np.ndarray, bg_thr: int, alpha: float = OVERLAY_ALPHA) -> bytes:
    """Blend the heat map onto the fundus (only where there is fundus), return JPEG bytes."""
    base = arr.astype(np.float32) / 255.0
    fundus = (arr.max(axis=2) > bg_thr)[..., None]
    # blended = np.where(fundus, (1 - alpha) * base + alpha * jet(np.clip(cam, 0, 1)), base)
        # Opacity follows the heat: unattended fundus stays untinted, strong regions are clearly coloured (no uniform blue wash).
    a = (alpha / OVERLAY_ALPHA * 0.65 * np.clip(cam / 0.35, 0, 1))[..., None]
    blended = np.where(fundus, (1 - a) * base + a * jet(np.clip(cam, 0, 1)), base)
    buf = io.BytesIO()
    Image.fromarray((np.clip(blended, 0, 1) * 255).astype(np.uint8)).save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def explain(screener, image_path, target: str) -> GradCamResult:
    t0 = time.perf_counter()
    idx = screener.idx[target_label(target)]
    arr, _crop_ok = screener.preprocess(str(image_path))
    cam, grid, empty = compute_cam(screener, arr, idx)
    return GradCamResult(target=target, overlay_jpeg=render_overlay(arr, cam, screener.cfg["bg_thr"]), resolution=int(arr.shape[0]), grid_size=grid,
                         empty=empty, inference_ms=int((time.perf_counter() - t0) * 1000))
