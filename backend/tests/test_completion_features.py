from io import BytesIO


def _login(client, email, password="ResQNetDemo!2026"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_image_classification_has_honest_unconfigured_fallback(client, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes.settings, "gemini_api_key", "")
    token = _login(client, "citizen@resqnet.demo")
    png_signature = b"\x89PNG\r\n\x1a\n" + b"synthetic-test-image"
    response = client.post(
        "/api/v1/ai/classify-image",
        headers=token,
        files={"file": ("animal.png", BytesIO(png_signature), "image/png")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available"] is False
    assert data["classification"] is None
    assert "manually" in data["message"]


def test_handoff_list_is_available_to_coordinator(client):
    token = _login(client, "coordinator@resqnet.demo")
    response = client.get("/api/v1/coordinator/handoffs", headers=token)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_admin_can_toggle_user_active_state(client):
    admin = _login(client, "admin@resqnet.demo")
    users = client.get("/api/v1/admin/users", headers=admin)
    assert users.status_code == 200, users.text
    citizen = next(user for user in users.json() if user["email"] == "citizen@resqnet.demo")
    disabled = client.patch(f"/api/v1/admin/users/{citizen['id']}/status", headers=admin, json={"is_active": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_active"] is False
    login_response = client.post("/api/v1/auth/login", json={"email": "citizen@resqnet.demo", "password": "ResQNetDemo!2026"})
    assert login_response.status_code == 403


def test_admin_cannot_deactivate_own_account(client):
    admin = _login(client, "admin@resqnet.demo")
    me = client.get("/api/v1/auth/me", headers=admin).json()
    response = client.patch(f"/api/v1/admin/users/{me['id']}/status", headers=admin, json={"is_active": False})
    assert response.status_code == 409


def test_reporter_can_confirm_voice_transcript(client):
    token = _login(client, "citizen@resqnet.demo")
    created = client.post("/api/v1/cases", headers=token, json={
        "animal_category": "Dog", "description": "A dog is injured near Salem bus stand.",
    })
    assert created.status_code == 201, created.text
    public_id = created.json()["public_id"]
    saved = client.patch(f"/api/v1/cases/{public_id}/voice-transcript", headers=token,
                         json={"transcript": "The dog is near the main bus stand."})
    assert saved.status_code == 200, saved.text
    assert "reporter-confirmed" in saved.json()["description"]


def test_other_citizen_cannot_change_voice_transcript(client):
    from app.core.security import hash_password
    from app.core.database import SessionLocal
    from app.models.entities import User, UserRole
    token = _login(client, "citizen@resqnet.demo")
    created = client.post("/api/v1/cases", headers=token, json={
        "animal_category": "Dog", "description": "A dog is injured near Salem bus stand.",
    })
    other = client.post("/api/v1/auth/register", json={"full_name":"Other Citizen", "email":"other.voice@test.com", "password":"StrongPass!2026", "role":"citizen"})
    other_token = {"Authorization": f"Bearer {other.json()['access_token']}"}
    response = client.patch(f"/api/v1/cases/{created.json()['public_id']}/voice-transcript", headers=other_token,
                            json={"transcript":"A different reporter transcript."})
    assert response.status_code == 404


def test_evidence_upload_persists_gps_and_supports_authorized_download(client):
    from io import BytesIO
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models.entities import RescueEvidence, Case
    from test_stage6_evidence import _setup_full_case, _auth

    setup = _setup_full_case(client)
    png = b"\x89PNG\r\n\x1a\n" + b"resqnet-test-image-bytes"
    uploaded = client.post(
        f"/api/v1/cases/{setup['public_id']}/evidence",
        headers=_auth(setup["rescuer_token"]),
        data={"evidence_type": "after_photo", "gps_lat": "11.6643", "gps_lon": "78.1460"},
        files={"file": ("after.png", BytesIO(png), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()["id"]
    with SessionLocal() as db:
        evidence = db.get(RescueEvidence, evidence_id)
        assert evidence.gps_latitude == 11.6643
        assert evidence.gps_longitude == 78.1460
        assert evidence.file_hash
    downloaded = client.get(
        f"/api/v1/cases/{setup['public_id']}/evidence/{evidence_id}/file",
        headers=_auth(setup["coord_token"]),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == png


def test_admin_can_create_coordinator_account_for_existing_organization(client):
    admin = _login(client, "admin@resqnet.demo")
    organizations = client.get("/api/v1/coordinator/organizations", headers=admin)
    assert organizations.status_code == 200
    org_id = organizations.json()[0]["id"]
    created = client.post("/api/v1/admin/users", headers=admin, json={
        "full_name": "New NGO Coordinator", "email": "new.coordinator@test.com",
        "password": "SecureTestPass!2026", "role": "coordinator", "organization_id": org_id,
    })
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "coordinator"
    login = client.post("/api/v1/auth/login", json={"email": "new.coordinator@test.com", "password": "SecureTestPass!2026"})
    assert login.status_code == 200


def test_admin_can_verify_responder_account(client):
    admin = _login(client, "admin@resqnet.demo")
    created = client.post("/api/v1/admin/users", headers=admin, json={
        "full_name": "New Responder", "email": "new.responder@test.com",
        "password": "SecureTestPass!2026", "role": "rescuer",
    })
    assert created.status_code == 201, created.text
    verified = client.patch(f"/api/v1/admin/users/{created.json()['id']}/verification", headers=admin, json={"verified": True})
    assert verified.status_code == 200, verified.text
    assert verified.json()["is_verified"] is True
