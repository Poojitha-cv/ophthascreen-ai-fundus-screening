"""Shared fixtures.

Test images are SYNTHETIC and exist only to exercise upload/quality/storage plumbing. Model outputs on
them are meaningless; tests assert structure and wiring, never clinical correctness. Most tests use a
deterministic test double (StubEngine) for speed; tests/test_model_integration.py uses the real weights.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

from app.core.config import Settings
from app.main import create_app
from app.modules.auth import service as auth_service
from app.modules.auth.models import Role
from app.modules.inference.protocol import FundusPrediction, ModelInfo

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "convnext_tiny_v1"
PASSWORD = "correct-horse-battery"


# ---------- synthetic images ----------

def fundus_like(size=(1200, 1000), seed=0, blur=0.0, brightness=1.0, tint=(1.0, 1.0, 1.0)) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = size
    im = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(min(w, h) * 0.48)
    cx, cy = w // 2, h // 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(185, 95, 45))
    for _ in range(40):  # vessel-like dark strokes
        pts = [(cx + rng.integers(-r, r), cy + rng.integers(-r, r)) for _ in range(4)]
        d.line(pts, fill=(95, 35, 20), width=int(rng.integers(3, 7)))
    arr = np.asarray(im).astype(np.float32)
    inside = arr.max(axis=2) > 0
    arr[inside] += rng.normal(0, 3, size=(inside.sum(), 3))
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(im).astype(np.float32) * np.array(tint, dtype=np.float32) * brightness
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def to_bytes(im: Image.Image, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def png(**kw) -> bytes:
    return to_bytes(fundus_like(**kw))


# ---------- test double for the model ----------

class StubEngine:
    """Deterministic stand-in with the engine interface. Thresholds come from the real inference_config.json."""

    def __init__(self):
        cfg = json.loads((MODEL_DIR / "inference_config.json").read_text())
        self.info = ModelInfo(tag="stub", weights_sha256="0" * 64, meta={
            k: cfg[k] for k in ("temperature", "risk_thr_maxF1", "risk_thr_sens95", "review_confidence_cutoff", "core_classes",
                                "disease_thr_global", "disease_thr_per_class", "embedding_dim")})
        self.disease_cols = cfg["disease_cols"]
        self.disease_names: dict[str, str] = {}
        self.risk, self.needs_review, self.flagged, self.fail = 0.9, False, ["DR"], False
        self.calls = 0

    def predict_one(self, image_path) -> FundusPrediction:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        probs = {c: 0.01 for c in self.disease_cols}
        for c in self.flagged:
            probs[c] = 0.9
        m = self.info.meta
        return FundusPrediction(
            risk_prob=self.risk, risk_abnormal_maxf1=self.risk >= m["risk_thr_maxF1"], risk_abnormal_screening=self.risk >= m["risk_thr_sens95"],
            risk_confidence=1.0, needs_review=self.needs_review, flagged_diseases=list(self.flagged), disease_probs=probs,
            crop_ok=True, warnings=[], embedding=np.zeros(768, dtype=np.float32), inference_ms=1)


# ---------- app fixtures ----------

def make_settings(tmp_path: Path, **over) -> Settings:
    base = dict(env="test", secret_key="k" * 40, database_url=f"sqlite:///{tmp_path / 'test.db'}", storage_dir=tmp_path / "images",
                model_dir=MODEL_DIR, login_max_failures=3)
    base.update(over)
    return Settings(**base)


@pytest.fixture
def stub():
    return StubEngine()


@pytest.fixture
def client(tmp_path, stub):
    app = create_app(make_settings(tmp_path), engine_loader=lambda s: stub)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_model(tmp_path):
    app = create_app(make_settings(tmp_path), engine_loader=lambda s: None)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_client(tmp_path, stub):
    """Factory for tests that need non-default settings."""
    clients = []

    def _make(**over):
        app = create_app(make_settings(tmp_path, **over), engine_loader=lambda s: stub)
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c
    yield _make
    for c in clients:
        c.__exit__(None, None, None)


# ---------- helpers ----------

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str, password: str = PASSWORD) -> str:
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register_patient(client, email="pat@clinic.org", name="Pat Ient", dob="1980-05-17") -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": name, "date_of_birth": dob})
    assert r.status_code == 201, r.text
    return {"email": email, "patient_id": r.json()["patient_id"], "user_id": r.json()["id"], "token": login(client, email)}


def make_doctor(client, email="dr@clinic.org", name="Dr. Test") -> str:
    with client.app.state.session_factory() as db:
        auth_service.create_user(db, email=email, password=PASSWORD, full_name=name, role=Role.DOCTOR)
        db.commit()
    return login(client, email)


def upload(client, token, patient_id, left=None, right=None):
    files = {}
    if left is not None:
        files["left_image"] = ("left.png", left, "image/png")
    if right is not None:
        files["right_image"] = ("right.png", right, "image/png")
    return client.post(f"/api/v1/patients/{patient_id}/screenings", files=files, headers=auth(token))
