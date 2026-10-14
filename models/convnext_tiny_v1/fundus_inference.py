"""Fundus-image component (ConvNeXt-Tiny fine-tuned on RFMiD). Read MODEL_CARD.md for limits.
Usage:
    from fundus_inference import FundusScreener
    s = FundusScreener("/path/to/export_dir")
    out = s.predict(["a.png", "b.jpg"], return_embedding=True)
"""
import json, os
import numpy as np
import torch
import torch.nn.functional as F
import timm
from PIL import Image


def _logit(p, eps=1e-6):
    p = float(np.clip(p, eps, 1 - eps))
    return float(np.log(p / (1 - p)))


class FundusScreener:
    def __init__(self, export_dir, device=None):
        with open(os.path.join(export_dir, "inference_config.json")) as f:
            self.cfg = json.load(f)
        c = self.cfg
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model = timm.create_model(c["model_name"], pretrained=False, num_classes=len(c["label_cols"]))
        sd = torch.load(os.path.join(export_dir, "model_weights.pt"), map_location="cpu", weights_only=True)
        self.model.load_state_dict(sd)
        self.model = self.model.to(self.device).eval().to(memory_format=torch.channels_last)
        self.mean = torch.tensor(c["mean"], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor(c["std"], device=self.device).view(1, 3, 1, 1)
        self.idx = {n: i for i, n in enumerate(c["label_cols"])}

    def preprocess(self, image):
        """path or PIL image -> (uint8 [S,S,3] array, crop_ok). Same crop/pad/resize as training cache."""
        c = self.cfg
        S, thr, red = c["cache_size"], c["bg_thr"], c["reduce"]
        im = Image.open(image) if isinstance(image, (str, os.PathLike)) else image
        im = im.convert("RGB")
        w, h = im.size
        small = np.asarray(im.reduce(red))
        m = small.max(axis=2) > thr
        cols = np.where(m.sum(axis=0) >= 3)[0]
        rows = np.where(m.sum(axis=1) >= 3)[0]
        if len(cols) == 0 or len(rows) == 0:
            x0, y0, x1, y1, ok = 0, 0, w, h, False
        else:
            x0 = max(0, (cols[0] - 1) * red); x1 = min(w, (cols[-1] + 2) * red)
            y0 = max(0, (rows[0] - 1) * red); y1 = min(h, (rows[-1] + 2) * red)
            ok = True
        crop = im.crop((x0, y0, x1, y1))
        cw, ch = crop.size
        sc = S / max(cw, ch)
        nw, nh = max(1, round(cw * sc)), max(1, round(ch * sc))
        crop = crop.resize((nw, nh), Image.LANCZOS, reducing_gap=3.0)
        canvas = Image.new("RGB", (S, S), (0, 0, 0))
        canvas.paste(crop, ((S - nw) // 2, (S - nh) // 2))
        return np.asarray(canvas), ok

    def _to_tensor(self, arrs):
        x = torch.from_numpy(np.stack(arrs)).to(self.device).permute(0, 3, 1, 2).contiguous().float().div_(255.0)
        s = self.cfg["img"]
        if x.shape[-1] != s:
            x = F.interpolate(x, size=(s, s), mode="bilinear", antialias=True, align_corners=False)
        return ((x - self.mean) / self.std).contiguous(memory_format=torch.channels_last)

    @torch.no_grad()
    def _forward(self, x):
        with torch.autocast(self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"):
            feats = self.model.forward_features(x)
            emb = self.model.forward_head(feats, pre_logits=True)
            logits = self.model.get_classifier()(emb)
        return logits.float().cpu(), emb.float().cpu()

    def _format(self, p, crop_ok, emb):
        c = self.cfg
        risk = float(p[0])
        conf = abs(_logit(risk) - _logit(c["risk_thr_maxF1"]))
        dp = {n: float(p[self.idx[n]]) for n in c["disease_cols"]}
        thr = lambda n: c["disease_thr_per_class"].get(n, c["disease_thr_global"])
        warn = [] if crop_ok else ["no fundus region found by the border-crop step; result unreliable"]
        out = dict(risk_prob=risk,
                   risk_abnormal_maxF1=risk >= c["risk_thr_maxF1"],
                   risk_abnormal_screening=risk >= c["risk_thr_sens95"],
                   risk_confidence=conf,
                   needs_review=bool(conf < c["review_confidence_cutoff"] or not crop_ok),
                   flagged_diseases=[n for n in c["core_classes"] if dp[n] >= thr(n)],
                   disease_probs=dp, crop_ok=crop_ok, warnings=warn)
        if emb is not None:
            out["embedding"] = emb.astype(np.float32)
        return out

    def predict(self, images, batch_size=16, return_embedding=False):
        results = []
        for i in range(0, len(images), batch_size):
            chunk = images[i:i + batch_size]
            pre = [self.preprocess(im) for im in chunk]
            logits, emb = self._forward(self._to_tensor([a for a, _ in pre]))
            probs = torch.sigmoid(logits / self.cfg["temperature"]).numpy()
            for k in range(len(chunk)):
                results.append(self._format(probs[k], pre[k][1], emb[k].numpy() if return_embedding else None))
        return results
