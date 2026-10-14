from tests.conftest import PASSWORD, auth, login, make_doctor, register_patient


def test_register_login_me(client):
    p = register_patient(client)
    me = client.get("/api/v1/auth/me", headers=auth(p["token"])).json()
    assert me["role"] == "patient" and me["patient_id"] == p["patient_id"] and me["email"] == "pat@clinic.org"


def test_register_cannot_choose_role(client):
    r = client.post("/api/v1/auth/register", json={"email": "x@clinic.org", "password": PASSWORD, "full_name": "X", "date_of_birth": "1990-01-01", "role": "doctor"})
    assert r.status_code == 201 and r.json()["role"] == "patient"


def test_register_validation(client):
    base = {"email": "a@clinic.org", "password": PASSWORD, "full_name": "A", "date_of_birth": "1990-01-01"}
    assert client.post("/api/v1/auth/register", json={**base, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "date_of_birth": "2999-01-01"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**base, "email": "not-an-email"}).status_code == 422


def test_duplicate_email_case_insensitive(client):
    register_patient(client, email="dup@clinic.org")
    r = client.post("/api/v1/auth/register", json={"email": "DUP@clinic.org", "password": PASSWORD, "full_name": "B", "date_of_birth": "1990-01-01"})
    assert r.status_code == 409


def test_wrong_password_and_unknown_user_same_response(client):
    register_patient(client)
    a = client.post("/api/v1/auth/login", data={"username": "pat@clinic.org", "password": "wrong-password-1"})
    b = client.post("/api/v1/auth/login", data={"username": "nobody@clinic.org", "password": "wrong-password-1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_lockout_after_repeated_failures(client):
    register_patient(client)  # login_max_failures=3 in test settings
    for _ in range(3):
        assert client.post("/api/v1/auth/login", data={"username": "pat@clinic.org", "password": "wrong-password-1"}).status_code == 401
    # even the CORRECT password is refused while locked
    assert client.post("/api/v1/auth/login", data={"username": "pat@clinic.org", "password": PASSWORD}).status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth("garbage")).status_code == 401
    assert client.get("/api/v1/dashboard/summary").status_code == 401


def test_patient_cannot_use_doctor_endpoints(client):
    p = register_patient(client)
    for path in ("/api/v1/dashboard/summary", "/api/v1/dashboard/queue", "/api/v1/patients"):
        assert client.get(path, headers=auth(p["token"])).status_code == 403


def test_change_password_invalidates_old_tokens(client):
    p = register_patient(client)
    import time
    time.sleep(1.1)  # token iat has 1s resolution
    r = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "another-long-pass"}, headers=auth(p["token"]))
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=auth(p["token"])).status_code == 401
    assert login(client, "pat@clinic.org", "another-long-pass")
    r = client.post("/api/v1/auth/change-password", json={"current_password": "nope-nope-nope", "new_password": "yet-another-pass"},
                    headers=auth(login(client, "pat@clinic.org", "another-long-pass")))
    assert r.status_code == 400


def test_doctor_role_and_patient_enrolment(client):
    d = make_doctor(client)
    assert client.get("/api/v1/auth/me", headers=auth(d)).json()["role"] == "doctor"
    r = client.post("/api/v1/patients", json={"full_name": "Walk In", "date_of_birth": "1970-02-02", "medical_record_number": "MRN-1"}, headers=auth(d))
    assert r.status_code == 201 and r.json()["has_account"] is False
    dup = client.post("/api/v1/patients", json={"full_name": "Other", "date_of_birth": "1971-02-02", "medical_record_number": "MRN-1"}, headers=auth(d))
    assert dup.status_code == 409
    found = client.get("/api/v1/patients", params={"q": "walk"}, headers=auth(d)).json()
    assert found["total"] == 1
    assert client.get("/api/v1/patients", params={"q": "%"}, headers=auth(d)).json()["total"] == 0  # wildcard is escaped
