from app.core.database import Base, engine
from app.models.entities import UserRole

def _register(client, email="reporter@example.com"):
    r = client.post("/api/v1/auth/register", json={"full_name":"Test Reporter","email":email,"password":"SafePass!2026","role":"citizen"})
    assert r.status_code == 201
    return r.json()["access_token"]

def _login(client, email, password="ResQNetDemo!2026"):
    r = client.post("/api/v1/auth/login", json={"email":email,"password":password})
    assert r.status_code == 200
    return r.json()["access_token"]

def test_citizen_can_create_and_track_case(client):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"animal_category":"Dog","description":"Dog hit by vehicle and heavy bleeding near Salem bus stand","latitude":11.6643,"longitude":78.1460,"landmark":"Salem bus stand"}
    created = client.post("/api/v1/cases", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    case = created.json()
    assert case["public_id"].startswith("RQ-")
    assert case["status"] == "REPORTED"
    assert case["priority"] == "CRITICAL"
    assert case["needs_human_review"] is True
    assert len(case["events"]) == 1
    listed = client.get("/api/v1/cases", headers=headers)
    assert listed.status_code == 200 and len(listed.json()) == 1
    fetched = client.get(f"/api/v1/cases/{case['public_id']}", headers=headers)
    assert fetched.status_code == 200

def test_citizen_cannot_view_another_citizens_case(client):
    token1 = _register(client, "one@example.com")
    token2 = _register(client, "two@example.com")
    r = client.post("/api/v1/cases", json={"animal_category":"Cat","description":"Cat is limping and needs help"}, headers={"Authorization":f"Bearer {token1}"})
    public_id = r.json()["public_id"]
    denied = client.get(f"/api/v1/cases/{public_id}", headers={"Authorization":f"Bearer {token2}"})
    assert denied.status_code == 404

def test_coordinator_can_review_and_override_triage(client):
    citizen_token = _register(client)
    created = client.post("/api/v1/cases", json={"animal_category":"Dog","description":"Dog is limping near the market"}, headers={"Authorization":f"Bearer {citizen_token}"}).json()
    coord_token = _login(client, "coordinator@resqnet.demo")
    response = client.patch(f"/api/v1/cases/{created['public_id']}/triage", json={"priority":"HIGH","reason":"Caller confirmed visible bleeding; escalate for prompt assessment."}, headers={"Authorization":f"Bearer {coord_token}"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "TRIAGED"
    assert response.json()["priority"] == "HIGH"
    assert len(response.json()["events"]) == 2

def test_rescuer_sees_only_cases_with_their_pending_or_accepted_offers(client):
    token = _login(client, "rescuer@resqnet.demo")
    response = client.get("/api/v1/cases", headers={"Authorization":f"Bearer {token}"})
    assert response.status_code == 200 and response.json() == []

def test_duplicate_suggestion_never_merges(client):
    token = _register(client)
    headers = {"Authorization":f"Bearer {token}"}
    base = {"animal_category":"Dog","description":"Injured dog beside Salem central bus stand","latitude":11.6643,"longitude":78.1460}
    first = client.post("/api/v1/cases", json=base, headers=headers).json()
    second = client.post("/api/v1/cases", json={**base,"description":"Another report: dog appears injured near the bus stand","latitude":11.6644,"longitude":78.1461}, headers=headers).json()
    assert second["status"] == "REPORTED"
    assert any(x["public_id"] == first["public_id"] for x in second["possible_duplicates"])
    assert len(client.get("/api/v1/cases", headers=headers).json()) == 2

def test_photo_upload_validates_file_signature_and_stores_private_file(client, tmp_path, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes, "UPLOAD_DIR", tmp_path)
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    case = client.post("/api/v1/cases", json={"animal_category":"Dog","description":"Dog needs help near the market"}, headers=headers).json()
    bad = client.post(f"/api/v1/cases/{case['public_id']}/photo", headers=headers, files={"photo":("fake.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 415
    # Minimal valid PNG signature and IHDR-like payload are sufficient for this MIME/signature gate.
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    good = client.post(f"/api/v1/cases/{case['public_id']}/photo", headers=headers, files={"photo":("animal.png", png, "image/png")})
    assert good.status_code == 201, good.text
    assert good.json()["has_photo"] is True
    private_read = client.get(f"/api/v1/cases/{case['public_id']}/photo", headers=headers)
    assert private_read.status_code == 200
