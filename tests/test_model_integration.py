"""Tests against the REAL exported weights. Synthetic input => outputs are meaningless clinically; we verify
that the wrapper reproduces the bundle's own FundusScreener exactly, enforces integrity, and wires into the API."""
import importlib.util
import json
import shutil
import threading
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.modules.inference.engine import FundusEngine, ModelLoadError
from app.modules.screenings.models import Prediction
from tests.conftest import MODEL_DIR, auth, fundus_like, make_doctor, make_settings, register_patient, upload

pytestmark = pytest.mark.skipif(not (MODEL_DIR / "model_weights.pt").exists(), reason="run scripts/install_model.py first")


@pytest.fixture(scope="module")
def real_engine():
    return FundusEngine(MODEL_DIR)


@pytest.fixture(scope="module")
def raw_screener():
    spec = importlib.util.spec_from_file_location("bundle_fundus_inference", MODEL_DIR / "fundus_inference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FundusScreener(str(MODEL_DIR))


@pytest.fixture
def img_path(tmp_path):
    p = tmp_path / "plumbing.png"
    fundus_like(size=(1400, 1100), seed=11).save(p)
    return p


def fake_model_dir(tmp_path, **manifest_over):
    """Small files copied, 111 MB weights symlinked, so we can tamper with metadata cheaply."""
    d = tmp_path / "model_copy"
    d.mkdir()
    for f in MODEL_DIR.iterdir():
        if f.name == "model_weights.pt":
            (d / f.name).symlink_to(f)
        elif f.is_file():
            shutil.copy(f, d / f.name)
    if manifest_over:
        m = json.loads((d / "export_manifest.json").read_text())
        m.update(manifest_over)
        (d / "export_manifest.json").write_text(json.dumps(m))
    return d


def test_wrapper_reproduces_bundle_output_exactly(real_engine, raw_screener, img_path):
    mine = real_engine.predict_one(img_path)
    ref = raw_screener.predict([str(img_path)], return_embedding=True)[0]
    assert mine.risk_prob == pytest.approx(ref["risk_prob"], abs=1e-6)
    assert mine.risk_abnormal_screening == ref["risk_abnormal_screening"] and mine.risk_abnormal_maxf1 == ref["risk_abnormal_maxF1"]
    assert mine.needs_review == ref["needs_review"] and mine.flagged_diseases == ref["flagged_diseases"] and mine.crop_ok == ref["crop_ok"]
    assert set(mine.disease_probs) == set(ref["disease_probs"]) and len(mine.disease_probs) == 45
    assert all(mine.disease_probs[k] == pytest.approx(v, abs=1e-6) for k, v in ref["disease_probs"].items())
    assert mine.embedding.shape == (768,) and mine.embedding.dtype == np.float32
    assert np.allclose(mine.embedding, ref["embedding"], atol=1e-5)
    assert all(0.0 <= p <= 1.0 for p in mine.disease_probs.values()) and 0.0 <= mine.risk_prob <= 1.0


def test_engine_info_matches_manifest_and_config(real_engine):
    manifest = json.loads((MODEL_DIR / "export_manifest.json").read_text())
    cfg = json.loads((MODEL_DIR / "inference_config.json").read_text())
    assert real_engine.info.tag == "convnext_tiny_v1" and real_engine.info.weights_sha256 == manifest["weights_sha256"]
    m = real_engine.info.meta
    assert m["risk_thr_sens95"] == cfg["risk_thr_sens95"] and m["review_confidence_cutoff"] == cfg["review_confidence_cutoff"]
    assert m["core_classes"] == cfg["core_classes"] and m["temperature"] == 1.65


def test_tampered_weights_are_refused(tmp_path):
    with pytest.raises(ModelLoadError, match="SHA-256 mismatch"):
        FundusEngine(fake_model_dir(tmp_path, weights_sha256="0" * 64))


def test_missing_files_error_is_actionable(tmp_path):
    with pytest.raises(ModelLoadError, match="install_model"):
        FundusEngine(tmp_path)


def test_concurrent_inference_is_safe(real_engine, img_path):
    results, errors = [], []

    def work():
        try:
            results.append(real_engine.predict_one(img_path).risk_prob)
        except Exception as e:  # pragma: no cover
            errors.append(e)
    ts = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and len(results) == 4 and max(results) - min(results) < 1e-6


def test_optional_disease_names_file_is_used(tmp_path):
    d = fake_model_dir(tmp_path)
    (d / "disease_names.json").write_text(json.dumps({"DR": "name supplied by the project team"}))
    assert FundusEngine(d).disease_names == {"DR": "name supplied by the project team"}


def test_require_model_aborts_startup(tmp_path):
    from app.modules.inference.engine import load_engine
    app = create_app(make_settings(tmp_path, model_dir=tmp_path / "nope", require_model=True), engine_loader=load_engine)
    with pytest.raises(ModelLoadError):
        with TestClient(app):
            pass


def test_degrades_gracefully_without_model_by_default(tmp_path):
    from app.modules.inference.engine import load_engine
    app = create_app(make_settings(tmp_path, model_dir=tmp_path / "nope"), engine_loader=load_engine)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "degraded", "database": True, "model_loaded": False, "model_tag": None}


def test_end_to_end_with_real_model(tmp_path, real_engine, raw_screener):
    app = create_app(make_settings(tmp_path), engine_loader=lambda s: real_engine)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok", "database": True, "model_loaded": True, "model_tag": "convnext_tiny_v1"}
        d, p = make_doctor(c), register_patient(c)
        s = upload(c, p["token"], p["patient_id"], left=_png_bytes(21), right=_png_bytes(22)).json()
        assert [i["analysis_status"] for i in s["images"]] == ["completed", "completed"]
        img = c.get(f"/api/v1/images/{s['images'][0]['id']}", headers=auth(d)).json()
        pred = img["prediction"]
        assert pred["model_tag"] == "convnext_tiny_v1" and pred["model_weights_sha256"] == real_engine.info.weights_sha256
        # what the API reports == what the bundle's own screener computes on the stored original file
        stored = c.get(img["file_url"], headers=auth(d)).content
        tmp = tmp_path / "stored.png"
        tmp.write_bytes(stored)
        ref = raw_screener.predict([str(tmp)], return_embedding=True)[0]
        assert pred["risk_probability"] == pytest.approx(ref["risk_prob"], abs=1e-4)
        assert sorted(pred["flagged_diseases"]) == sorted(ref["flagged_diseases"])
        with app.state.session_factory() as db:
            row = db.scalars(select(Prediction).where(Prediction.id == pred["id"])).one()
            assert np.allclose(np.frombuffer(row.embedding, dtype=np.float32), ref["embedding"], atol=1e-5)


def _png_bytes(seed):
    from tests.conftest import png
    return png(size=(1400, 1100), seed=seed)
