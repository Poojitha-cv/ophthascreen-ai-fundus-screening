from tests.conftest import auth, make_doctor, png, register_patient, upload


def queue(client, token, **params):
    r = client.get("/api/v1/dashboard/queue", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def seed(client, stub):
    """Three patients, four images, different AI outputs. Returns doctor token + ids."""
    d = make_doctor(client)
    mk = lambda name, mrn: client.post("/api/v1/patients", json={"full_name": name, "date_of_birth": "1975-03-03", "medical_record_number": mrn}, headers=auth(d)).json()["id"]
    ids = {"alice": mk("Alice Alpha", "M-1"), "bob": mk("Bob Beta", "M-2"), "cy": mk("Cy Gamma", "M-3")}

    def up(who, risk, review, flagged, **kw):
        stub.risk, stub.needs_review, stub.flagged = risk, review, flagged
        return upload(client, d, ids[who], **kw).json()

    out = {
        "alice": up("alice", 0.95, False, ["DR"], left=png(seed=1)),
        "bob": up("bob", 0.05, False, [], right=png(seed=2)),
        "cy_unsure": up("cy", 0.30, True, [], left=png(seed=3)),
        "cy_high": up("cy", 0.60, False, ["MH"], right=png(seed=4)),
    }
    return d, ids, out


def test_summary_counts(client, stub):
    d, ids, _ = seed(client, stub)
    s = client.get("/api/v1/dashboard/summary", headers=auth(d)).json()
    assert (s["patients_total"], s["screenings_total"], s["current_images_total"]) == (3, 4, 4)
    assert s["pending_review"] == 4 and s["pending_flagged_abnormal"] == 3   # 0.95, 0.60, 0.30 >= screening thr 0.1075
    assert s["pending_model_uncertain"] == 1 and s["reviewed_total"] == 0 and s["quality_failed"] == 0


def test_queue_priority_order_and_fields(client, stub):
    d, *_ = seed(client, stub)
    items = queue(client, d)["items"]
    # flagged first; among flagged, model-uncertain first, then by risk
    assert [round(i["risk_probability"], 2) for i in items] == [0.30, 0.95, 0.60, 0.05]
    top = items[1]
    assert top["patient"]["full_name"] == "Alice Alpha" and top["flagged_diseases"] == ["DR"]
    assert top["top_core_diseases"][0] == {"code": "DR", "probability": 0.9} and top["review_status"] == "pending"
    assert queue(client, d, sort="risk")["items"][0]["risk_probability"] == 0.95
    assert len(queue(client, d, sort="newest")["items"]) == 4


def test_queue_filters_and_pagination(client, stub):
    d, ids, _ = seed(client, stub)
    assert queue(client, d, eye="left")["total"] == 2
    assert queue(client, d, abnormal=False)["total"] == 1
    assert queue(client, d, needs_review=True)["total"] == 1
    assert queue(client, d, q="gamma")["total"] == 2 and queue(client, d, q="M-2")["total"] == 1
    assert queue(client, d, patient_id=ids["alice"])["total"] == 1
    assert queue(client, d, date_from="2999-01-01")["total"] == 0
    p1 = queue(client, d, size=3)
    assert p1["total"] == 4 and len(p1["items"]) == 3 and len(queue(client, d, size=3, page=2)["items"]) == 1
    assert client.get("/api/v1/dashboard/queue", params={"size": 1000}, headers=auth(d)).status_code == 422


def test_review_flow(client, stub):
    d, ids, out = seed(client, stub)
    item = queue(client, d, patient_id=ids["alice"])["items"][0]
    r = client.post(f"/api/v1/predictions/{item['prediction_id']}/reviews", headers=auth(d),
                    json={"decision": "agree", "impression": "abnormal", "comment": "  Consistent with AI.  "})
    assert r.status_code == 201 and r.json()["comment"] == "Consistent with AI." and r.json()["doctor_name"] == "Dr. Test"
    assert queue(client, d)["total"] == 3
    rv = queue(client, d, status="reviewed")["items"]
    assert len(rv) == 1 and rv[0]["last_review"]["decision"] == "agree" and rv[0]["review_status"] == "reviewed"
    # a correction is appended; newest wins, history is kept
    client.post(f"/api/v1/predictions/{item['prediction_id']}/reviews", headers=auth(d), json={"decision": "disagree", "impression": "normal"})
    assert queue(client, d, status="reviewed")["items"][0]["last_review"]["decision"] == "disagree"
    detail = client.get(f"/api/v1/images/{item['image_id']}", headers=auth(d)).json()
    assert [x["decision"] for x in detail["reviews"]] == ["disagree", "agree"]
    assert len(client.get(f"/api/v1/predictions/{item['prediction_id']}/reviews", headers=auth(d)).json()) == 2
    assert client.get("/api/v1/dashboard/summary", headers=auth(d)).json()["reviewed_today_utc"] == 2


def test_review_validation_and_permissions(client, stub):
    d, ids, out = seed(client, stub)
    pid = queue(client, d)["items"][0]["prediction_id"]
    pat = register_patient(client)
    assert client.post(f"/api/v1/predictions/{pid}/reviews", headers=auth(pat["token"]), json={"decision": "agree"}).status_code == 403
    assert client.post(f"/api/v1/predictions/{pid}/reviews", headers=auth(d), json={"decision": "maybe"}).status_code == 422
    assert client.post(f"/api/v1/predictions/{pid}/reviews", headers=auth(d), json={"decision": "agree", "comment": "x" * 2001}).status_code == 422
    assert client.post("/api/v1/predictions/doesnotexist/reviews", headers=auth(d), json={"decision": "agree"}).status_code == 404


def test_reanalysis_supersedes_old_prediction_and_requeues(client, stub):
    d, ids, out = seed(client, stub)
    item = queue(client, d, patient_id=ids["alice"])["items"][0]
    client.post(f"/api/v1/predictions/{item['prediction_id']}/reviews", headers=auth(d), json={"decision": "agree"})
    stub.risk = 0.5
    again = client.post(f"/api/v1/images/{item['image_id']}/analyze", headers=auth(d)).json()
    assert again["prediction"]["id"] != item["prediction_id"] and again["review_status"] == "pending"
    # old prediction can no longer be reviewed; the new one is back in the pending queue
    assert client.post(f"/api/v1/predictions/{item['prediction_id']}/reviews", headers=auth(d), json={"decision": "agree"}).status_code == 409
    assert queue(client, d, patient_id=ids["alice"])["items"][0]["prediction_id"] == again["prediction"]["id"]
    assert queue(client, d, status="reviewed")["total"] == 0


def test_patient_sees_review_status_but_not_content(client, stub):
    d = make_doctor(client)
    p = register_patient(client)
    img = upload(client, p["token"], p["patient_id"], left=png()).json()["images"][0]
    pid = queue(client, d)["items"][0]["prediction_id"]
    client.post(f"/api/v1/predictions/{pid}/reviews", headers=auth(d), json={"decision": "disagree", "comment": "internal note"})
    seen = client.get(f"/api/v1/images/{img['id']}", headers=auth(p["token"])).json()
    assert seen["review_status"] == "reviewed" and seen["reviews"] == [] and seen["prediction"] is None
    assert "internal note" not in client.get(f"/api/v1/patients/{p['patient_id']}/screenings", headers=auth(p["token"])).text
