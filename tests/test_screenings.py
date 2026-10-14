import io

from PIL import Image
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.modules.screenings.models import FundusImage, Prediction, Screening
from tests.conftest import auth, fundus_like, make_doctor, png, register_patient, to_bytes, upload


def counts(client):
    with client.app.state.session_factory() as db:
        return [db.scalar(select(func.count()).select_from(m)) for m in (Screening, FundusImage, Prediction)]


def stored_files(client):
    return [p for p in client.app.state.settings.storage_dir.rglob("*") if p.is_file()]


def test_patient_uploads_both_eyes(client, stub):
    p = register_patient(client)
    r = upload(client, p["token"], p["patient_id"], left=png(seed=1), right=png(seed=2))
    assert r.status_code == 201, r.text
    body = r.json()
    assert {i["eye"] for i in body["images"]} == {"left", "right"}
    for img in body["images"]:
        assert img["quality"]["status"] == "pass" and img["analysis_status"] == "completed"
        assert img["review_status"] == "pending"
        assert img["prediction"] is None and img["quality"]["metrics"] is None  # hidden from patients by default
    assert stub.calls == 2 and counts(client) == [1, 2, 2] and len(stored_files(client)) == 2


def test_doctor_sees_full_prediction(client, stub):
    stub.risk, stub.flagged = 0.8, ["DR", "MH"]
    d, p = make_doctor(client), register_patient(client)
    s = upload(client, p["token"], p["patient_id"], right=png()).json()
    img = client.get(f"/api/v1/images/{s['images'][0]['id']}", headers=auth(d)).json()
    pr = img["prediction"]
    assert pr["risk_probability"] == 0.8 and pr["risk_abnormal_screening"] is True
    assert pr["flagged_diseases"] == ["DR", "MH"] and "Research prototype" in pr["notice"]
    assert len(pr["diseases"]) == 45 and pr["diseases"][0]["flagged"] is True
    core = {x["code"]: x for x in pr["diseases"]}
    assert core["DR"]["validated"] and core["DR"]["threshold"] == 0.75   # threshold from the model's own config
    assert not core["TV"]["validated"] and core["TV"]["threshold"] is None  # non-core: probability only
    assert img["quality"]["metrics"]["fov_fraction"] > 0


def test_patient_can_see_ai_when_policy_allows(make_client):
    c = make_client(patient_can_see_ai_results=True)
    p = register_patient(c)
    s = upload(c, p["token"], p["patient_id"], left=png()).json()
    assert s["images"][0]["prediction"] is not None


def test_prediction_snapshot_and_embedding_stored(client):
    p = register_patient(client)
    upload(client, p["token"], p["patient_id"], left=png())
    with client.app.state.session_factory() as db:
        pred = db.scalar(select(Prediction))
        assert pred.model_meta["risk_thr_sens95"] > 0 and pred.model_tag == "stub"
        assert len(pred.embedding) == 768 * 4


def test_requires_at_least_one_image(client):
    p = register_patient(client)
    assert upload(client, p["token"], p["patient_id"]).status_code == 400
    assert counts(client) == [0, 0, 0]


def test_invalid_uploads_rejected_atomically(client):
    p = register_patient(client)
    # valid left + corrupt right => NOTHING stored
    files = {"left_image": ("l.png", png(), "image/png"), "right_image": ("r.png", b"this is not an image", "image/png")}
    r = client.post(f"/api/v1/patients/{p['patient_id']}/screenings", files=files, headers=auth(p["token"]))
    assert r.status_code == 400 and "right_image" in r.json()["detail"]
    assert counts(client) == [0, 0, 0] and stored_files(client) == []
    gif = to_bytes(fundus_like(size=(600, 600)), "GIF")
    assert upload(client, p["token"], p["patient_id"], left=gif).status_code == 415
    assert client.post(f"/api/v1/patients/{p['patient_id']}/screenings", files={"left_image": ("e.png", b"", "image/png")}, headers=auth(p["token"])).status_code == 400
    assert counts(client) == [0, 0, 0]


def test_oversize_upload_rejected(make_client):
    c = make_client(max_upload_bytes=50_000)
    p = register_patient(c)
    assert upload(c, p["token"], p["patient_id"], left=png()).status_code == 413
    assert counts(c) == [0, 0, 0]


def test_truncated_image_rejected(client):
    p = register_patient(client)
    assert upload(client, p["token"], p["patient_id"], left=png()[:2000]).status_code == 400


def test_patient_isolation(client):
    a, b = register_patient(client, "a@clinic.org", "A"), register_patient(client, "b@clinic.org", "B")
    s = upload(client, a["token"], a["patient_id"], left=png()).json()
    img = s["images"][0]
    assert upload(client, b["token"], a["patient_id"], left=png()).status_code == 404
    assert client.get(f"/api/v1/patients/{a['patient_id']}", headers=auth(b["token"])).status_code == 404
    assert client.get(f"/api/v1/patients/{a['patient_id']}/screenings", headers=auth(b["token"])).status_code == 404
    assert client.get(f"/api/v1/screenings/{s['id']}", headers=auth(b["token"])).status_code == 404
    assert client.get(f"/api/v1/images/{img['id']}", headers=auth(b["token"])).status_code == 404
    assert client.get(f"/api/v1/images/{img['id']}/file", headers=auth(b["token"])).status_code == 404
    assert client.post(f"/api/v1/screenings/{s['id']}/images", data={"eye": "right"}, files={"image": ("x.png", png(), "image/png")}, headers=auth(b["token"])).status_code == 404
    assert client.get(f"/api/v1/images/{img['id']}/file", headers=auth(a["token"])).status_code == 200


def test_original_bytes_preserved_and_preview(client):
    raw = png(seed=7)
    d, p = make_doctor(client), register_patient(client)
    img = upload(client, p["token"], p["patient_id"], left=raw).json()["images"][0]
    r = client.get(img["file_url"], headers=auth(d))
    assert r.content == raw and r.headers["content-type"] == "image/png" and "no-store" in r.headers["cache-control"]
    pv = client.get(img["file_url"], params={"max_side": 256}, headers=auth(d))
    assert pv.headers["content-type"] == "image/jpeg" and max(Image.open(io.BytesIO(pv.content)).size) == 256


def test_same_file_for_both_eyes_and_duplicates_warn(client):
    p = register_patient(client)
    raw = png(seed=4)
    s = upload(client, p["token"], p["patient_id"], left=raw, right=raw).json()
    by_eye = {i["eye"]: i for i in s["images"]}
    assert "identical_file_used_for_other_eye" in {x["code"] for x in by_eye["right"]["quality"]["issues"]}
    assert by_eye["right"]["quality"]["status"] == "warn"
    s2 = upload(client, p["token"], p["patient_id"], left=raw).json()  # later visit, same file again
    assert any(x["code"] == "identical_file_used_for_other_eye" for x in s2["images"][0]["quality"]["issues"])


def test_quality_fail_is_stored_but_not_analysed(client, stub):
    black = to_bytes(fundus_like(size=(900, 900), brightness=0.0))
    p = register_patient(client)
    img = upload(client, p["token"], p["patient_id"], left=black).json()["images"][0]
    assert img["quality"]["status"] == "fail" and img["analysis_status"] == "skipped_quality" and img["review_status"] is None
    assert stub.calls == 0 and counts(client) == [1, 1, 0]
    d = make_doctor(client)
    q = client.get("/api/v1/dashboard/queue", params={"status": "quality_failed"}, headers=auth(d)).json()
    assert q["total"] == 1 and q["items"][0]["prediction_id"] is None
    assert client.post(f"/api/v1/images/{img['id']}/analyze", headers=auth(d)).status_code == 409


def test_retake_supersedes_but_keeps_history(client):
    p = register_patient(client)
    s = upload(client, p["token"], p["patient_id"], left=png(seed=1)).json()
    old = s["images"][0]
    new = client.post(f"/api/v1/screenings/{s['id']}/images", data={"eye": "left"}, files={"image": ("l2.png", png(seed=2), "image/png")}, headers=auth(p["token"]))
    assert new.status_code == 201 and new.json()["is_current"] is True
    cur = client.get(f"/api/v1/screenings/{s['id']}", headers=auth(p["token"])).json()
    assert [i["id"] for i in cur["images"]] == [new.json()["id"]]
    allv = client.get(f"/api/v1/screenings/{s['id']}", params={"include_superseded": True}, headers=auth(p["token"])).json()
    assert {i["id"] for i in allv["images"]} == {old["id"], new.json()["id"]}
    assert len(stored_files(client)) == 2
    # the missing eye can be added later too
    assert client.post(f"/api/v1/screenings/{s['id']}/images", data={"eye": "right"}, files={"image": ("r.png", png(seed=3), "image/png")}, headers=auth(p["token"])).status_code == 201


def test_history_newest_first_and_paginated(client):
    p = register_patient(client)
    ids = [upload(client, p["token"], p["patient_id"], left=png(seed=i)).json()["id"] for i in range(3)]
    h = client.get(f"/api/v1/patients/{p['patient_id']}/screenings", params={"size": 2}, headers=auth(p["token"])).json()
    assert h["total"] == 3 and [s["id"] for s in h["items"]] == [ids[2], ids[1]]
    h2 = client.get(f"/api/v1/patients/{p['patient_id']}/screenings", params={"size": 2, "page": 2}, headers=auth(p["token"])).json()
    assert [s["id"] for s in h2["items"]] == [ids[0]]


def test_model_unavailable_then_reanalyse(client_no_model, tmp_path):
    c = client_no_model
    p, d = register_patient(c), make_doctor(c)
    img = upload(c, p["token"], p["patient_id"], left=png()).json()["images"][0]
    assert img["analysis_status"] == "pending" and img["review_status"] is None
    assert c.get("/health").json()["model_loaded"] is False
    assert c.post(f"/api/v1/images/{img['id']}/analyze", headers=auth(d)).status_code == 503
    inc = c.get("/api/v1/dashboard/queue", params={"status": "analysis_incomplete"}, headers=auth(d)).json()
    assert inc["total"] == 1


def test_inference_error_is_recorded_and_retryable(client, stub):
    stub.fail = True
    p, d = register_patient(client), make_doctor(client)
    r = upload(client, p["token"], p["patient_id"], left=png())
    assert r.status_code == 201                       # the upload itself is safe
    img = r.json()["images"][0]
    assert img["analysis_status"] == "failed" and counts(client) == [1, 1, 0]
    stub.fail = False
    again = client.post(f"/api/v1/images/{img['id']}/analyze", headers=auth(d)).json()
    assert again["analysis_status"] == "completed" and again["prediction"] is not None


def test_audit_trail(client):
    d, p = make_doctor(client), register_patient(client)
    img = upload(client, p["token"], p["patient_id"], left=png()).json()["images"][0]
    client.get(img["file_url"], headers=auth(d))
    with client.app.state.session_factory() as db:
        actions = [a.action for a in db.scalars(select(AuditLog))]
    for expected in ("auth.register", "auth.login", "screening.create", "image.view"):
        assert expected in actions
