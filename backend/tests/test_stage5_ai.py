"""Stage 5 tests: AI extraction, audio upload, AI status endpoint."""
from io import BytesIO
import pytest


def _register(client, email, role="citizen", name="Test User"):
    return client.post("/api/v1/auth/register", json={
        "full_name": name, "email": email, "password": "StrongPass!2026",
        "role": role,
    })


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass!2026"})
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestDeterministicExtraction:
    def test_dog_bleeding(self):
        from app.services.ai_extraction import extract_incident
        result = extract_incident("There is a black dog near the Salem bus stand. It was hit by a vehicle and cannot stand. There is bleeding near its leg.")
        assert result.animal_category == "dog"
        assert result.animal_color == "black"
        assert result.suggested_priority == "CRITICAL"
        assert result.source == "deterministic"
        assert result.confidence_score > 0
        assert "bleeding" in (result.injury_description or "")

    def test_cat_injured(self):
        from app.services.ai_extraction import extract_incident
        result = extract_incident("An injured cat is stuck on a roof near the temple")
        assert result.animal_category == "cat"
        assert "stuck" in (result.injury_description or "").lower() or "injured" in (result.injury_description or "").lower()

    def test_empty_string(self):
        from app.services.ai_extraction import extract_incident
        result = extract_incident("")
        assert result is not None
        assert result.suggested_priority in ("NEEDS_REVIEW", "MEDIUM")

    def test_gibberish(self):
        from app.services.ai_extraction import extract_incident
        result = extract_incident("asdf jkl qwerty zxcv 12345")
        assert result is not None
        assert result.needs_human_review is True

    def test_tamil_text_no_crash(self):
        from app.services.ai_extraction import extract_incident
        result = extract_incident("ஒரு நாய் சாலையில் அடிபட்டு கிடக்கிறது")
        assert result is not None


class TestAIEndpoints:
    def test_ai_status(self, client):
        _register(client, "ai_citizen@test.com")
        token = _login(client, "ai_citizen@test.com")
        r = client.get("/api/v1/ai/status", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "features" in data
        assert data["features"]["incident_extraction"] is True

    def test_ai_status_requires_auth(self, client):
        r = client.get("/api/v1/ai/status")
        assert r.status_code in (401, 403)

    def test_extract_incident_endpoint(self, client):
        _register(client, "ai_citizen2@test.com")
        token = _login(client, "ai_citizen2@test.com")
        r = client.post("/api/v1/ai/extract-incident",
            json={"text": "A dog is bleeding near Salem railway station"},
            headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["animal_category"] == "dog"
        assert data["suggested_priority"] == "CRITICAL"

    def test_extract_empty_text(self, client):
        _register(client, "ai_citizen3@test.com")
        token = _login(client, "ai_citizen3@test.com")
        r = client.post("/api/v1/ai/extract-incident",
            json={"text": ""},
            headers=_auth(token))
        assert r.status_code == 422

    def test_audio_upload_bad_mime(self, client):
        _register(client, "audio_citizen@test.com")
        token = _login(client, "audio_citizen@test.com")
        # First create a case
        r = client.post("/api/v1/cases",
            json={"animal_category": "dog", "description": "Test dog case for audio"},
            headers=_auth(token))
        assert r.status_code == 201
        public_id = r.json()["public_id"]
        # Upload with bad MIME
        r = client.post(f"/api/v1/cases/{public_id}/audio-report",
            files={"audio": ("test.txt", BytesIO(b"not audio"), "text/plain")},
            headers=_auth(token))
        assert r.status_code == 415


class TestDuplicateDetection:
    def test_similarity_score_in_duplicates(self, client):
        _register(client, "dup_citizen@test.com")
        token = _login(client, "dup_citizen@test.com")
        # Create two cases with same location and category
        r1 = client.post("/api/v1/cases", json={
            "animal_category": "dog",
            "description": "Injured dog near Salem bus stand bleeding",
            "latitude": 11.6643, "longitude": 78.1460,
        }, headers=_auth(token))
        assert r1.status_code == 201
        r2 = client.post("/api/v1/cases", json={
            "animal_category": "dog",
            "description": "Dog injured near Salem bus stand with blood",
            "latitude": 11.6643, "longitude": 78.1461,
        }, headers=_auth(token))
        assert r2.status_code == 201
        data = r2.json()
        if data.get("possible_duplicates"):
            assert "similarity_score" in data["possible_duplicates"][0]
