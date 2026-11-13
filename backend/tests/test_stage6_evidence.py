"""Stage 6 tests: evidence upload, verification, reliability, notifications."""
from io import BytesIO
import pytest


def _register(client, email, role="citizen", name="Test User"):
    return client.post("/api/v1/auth/register", json={
        "full_name": name, "email": email, "password": "Test1234!",
        "role": role,
    })


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Test1234!"})
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_full_case(client):
    """Create citizen, rescuer, coordinator, admin; create a case and assign it."""
    from app.core.database import get_db
    from app.models.entities import User, ResponderProfile, Availability, ResponderSkill, UserRole
    from sqlalchemy import select

    _register(client, "ev_citizen@test.com", "citizen", "EV Citizen")
    _register(client, "ev_rescuer@test.com", "rescuer", "EV Rescuer")
    _register(client, "ev_coord@test.com", "citizen", "EV Coordinator")
    _register(client, "ev_admin@test.com", "citizen", "EV Admin")

    # Directly set roles via DB for coordinator and admin
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        coord = db.scalar(select(User).where(User.email == "ev_coord@test.com"))
        coord.role = UserRole.COORDINATOR
        admin = db.scalar(select(User).where(User.email == "ev_admin@test.com"))
        admin.role = UserRole.ADMIN

        # Verify the rescuer
        rescuer = db.scalar(select(User).where(User.email == "ev_rescuer@test.com"))
        rescuer.is_verified = True
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == rescuer.id))
        from datetime import datetime, timezone
        profile.verified_at = datetime.now(timezone.utc)
        profile.latitude = 11.6643
        profile.longitude = 78.1460
        profile.service_radius_km = 50.0
        db.add(Availability(responder_id=profile.id, is_available=True))
        db.add(ResponderSkill(responder_id=profile.id, species="all"))
        db.commit()
    finally:
        db.close()

    # Login tokens
    citizen_token = _login(client, "ev_citizen@test.com")
    rescuer_token = _login(client, "ev_rescuer@test.com")
    coord_token = _login(client, "ev_coord@test.com")
    admin_token = _login(client, "ev_admin@test.com")

    # Create case
    r = client.post("/api/v1/cases", json={
        "animal_category": "dog",
        "description": "Test dog hit by vehicle near bus stand bleeding",
        "latitude": 11.6643, "longitude": 78.1460,
    }, headers=_auth(citizen_token))
    assert r.status_code == 201
    public_id = r.json()["public_id"]

    # Triage
    r = client.patch(f"/api/v1/cases/{public_id}/triage", json={
        "priority": "CRITICAL", "reason": "Dog hit by vehicle needs immediate help",
    }, headers=_auth(coord_token))
    assert r.status_code == 200

    # Assign
    r = client.post(f"/api/v1/coordinator/cases/{public_id}/assign",
                    headers=_auth(coord_token))
    assert r.status_code == 201
    offer_id = r.json()["offer_id"]

    # Accept
    r = client.post(f"/api/v1/responder/offers/{offer_id}/accept",
                    headers=_auth(rescuer_token))
    assert r.status_code == 200

    return {
        "public_id": public_id,
        "citizen_token": citizen_token,
        "rescuer_token": rescuer_token,
        "coord_token": coord_token,
        "admin_token": admin_token,
    }


class TestEvidenceSubmission:
    def test_submit_note_evidence(self, client):
        setup = _setup_full_case(client)
        r = client.post(
            f"/api/v1/cases/{setup['public_id']}/evidence",
            data={
                "evidence_type": "note",
                "rescue_notes": "Dog is stable, bleeding controlled",
                "animal_condition": "Conscious, leg injury",
            },
            headers=_auth(setup["rescuer_token"]),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["evidence_type"] == "note"
        assert data["has_file"] is False

    def test_submit_evidence_without_accepted_offer(self, client):
        _register(client, "no_offer_rescuer@test.com", "rescuer", "No Offer")
        token = _login(client, "no_offer_rescuer@test.com")
        r = client.post(
            "/api/v1/cases/FAKE-ID/evidence",
            data={"evidence_type": "note", "rescue_notes": "Test"},
            headers=_auth(token),
        )
        assert r.status_code in (403, 404)

    def test_get_evidence_list(self, client):
        setup = _setup_full_case(client)
        # Submit evidence
        client.post(
            f"/api/v1/cases/{setup['public_id']}/evidence",
            data={"evidence_type": "note", "rescue_notes": "Test note"},
            headers=_auth(setup["rescuer_token"]),
        )
        # Coordinator can see evidence
        r = client.get(
            f"/api/v1/cases/{setup['public_id']}/evidence",
            headers=_auth(setup["coord_token"]),
        )
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_citizen_cannot_see_evidence(self, client):
        setup = _setup_full_case(client)
        r = client.get(
            f"/api/v1/cases/{setup['public_id']}/evidence",
            headers=_auth(setup["citizen_token"]),
        )
        assert r.status_code == 403


class TestVerification:
    def test_verify_approved(self, client):
        setup = _setup_full_case(client)
        pid = setup["public_id"]
        rt = setup["rescuer_token"]
        ct = setup["coord_token"]

        # Progress through states
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "EN_ROUTE"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "ARRIVED"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "RESCUE_IN_PROGRESS"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "RESCUED"}, headers=_auth(rt))

        # Verify
        r = client.post(f"/api/v1/cases/{pid}/verify",
                        json={"decision": "APPROVED", "reason": "Evidence checks out, animal safe"},
                        headers=_auth(ct))
        assert r.status_code == 200
        assert r.json()["decision"] == "APPROVED"
        assert r.json()["case_status"] == "VERIFIED"

    def test_citizen_cannot_verify(self, client):
        setup = _setup_full_case(client)
        r = client.post(f"/api/v1/cases/{setup['public_id']}/verify",
                        json={"decision": "APPROVED", "reason": "Looks good to me"},
                        headers=_auth(setup["citizen_token"]))
        assert r.status_code == 403

    def test_close_verified_case(self, client):
        setup = _setup_full_case(client)
        pid = setup["public_id"]
        rt = setup["rescuer_token"]
        ct = setup["coord_token"]

        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "EN_ROUTE"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "ARRIVED"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "RESCUE_IN_PROGRESS"}, headers=_auth(rt))
        client.patch(f"/api/v1/cases/{pid}/progress",
                     json={"status": "RESCUED"}, headers=_auth(rt))
        client.post(f"/api/v1/cases/{pid}/verify",
                    json={"decision": "APPROVED", "reason": "Evidence confirmed"},
                    headers=_auth(ct))
        r = client.post(f"/api/v1/cases/{pid}/close",
                        json={"reason": "Rescue complete, animal safe"},
                        headers=_auth(ct))
        assert r.status_code == 200
        assert r.json()["status"] == "CLOSED"


class TestNotifications:
    def test_get_notifications(self, client):
        _register(client, "notif_user@test.com")
        token = _login(client, "notif_user@test.com")
        r = client.get("/api/v1/notifications", headers=_auth(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_notification_count(self, client):
        _register(client, "notif_user2@test.com")
        token = _login(client, "notif_user2@test.com")
        r = client.get("/api/v1/notifications/count", headers=_auth(token))
        assert r.status_code == 200
        assert "unread" in r.json()


class TestReliability:
    def test_my_reliability(self, client):
        _register(client, "rel_rescuer@test.com", "rescuer", "Rel Rescuer")
        token = _login(client, "rel_rescuer@test.com")
        r = client.get("/api/v1/responder/my-reliability", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "score" in data
        assert data["score"] == 100.0


class TestAnalytics:
    def test_analytics_summary_as_admin(self, client):
        _register(client, "an_admin@test.com", "citizen", "Analytics Admin")
        from app.core.database import SessionLocal
        from app.models.entities import User, UserRole
        from sqlalchemy import select
        db = SessionLocal()
        try:
            u = db.scalar(select(User).where(User.email == "an_admin@test.com"))
            u.role = UserRole.ADMIN
            db.commit()
        finally:
            db.close()
        token = _login(client, "an_admin@test.com")
        r = client.get("/api/v1/analytics/summary", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "total_cases" in data
        assert "by_priority" in data
        assert "by_status" in data

    def test_analytics_requires_coordinator(self, client):
        _register(client, "an_citizen@test.com")
        token = _login(client, "an_citizen@test.com")
        r = client.get("/api/v1/analytics/summary", headers=_auth(token))
        assert r.status_code == 403


class TestProgressExtended:
    def test_full_progress_chain(self, client):
        setup = _setup_full_case(client)
        pid = setup["public_id"]
        rt = setup["rescuer_token"]

        r = client.patch(f"/api/v1/cases/{pid}/progress",
                         json={"status": "EN_ROUTE"}, headers=_auth(rt))
        assert r.status_code == 200
        assert r.json()["status"] == "EN_ROUTE"

        r = client.patch(f"/api/v1/cases/{pid}/progress",
                         json={"status": "ARRIVED"}, headers=_auth(rt))
        assert r.status_code == 200

        r = client.patch(f"/api/v1/cases/{pid}/progress",
                         json={"status": "RESCUE_IN_PROGRESS"}, headers=_auth(rt))
        assert r.status_code == 200

        r = client.patch(f"/api/v1/cases/{pid}/progress",
                         json={"status": "RESCUED"}, headers=_auth(rt))
        assert r.status_code == 200
        assert r.json()["status"] == "VERIFICATION_PENDING"

    def test_invalid_progress_transition(self, client):
        setup = _setup_full_case(client)
        r = client.patch(f"/api/v1/cases/{setup['public_id']}/progress",
                         json={"status": "CLOSED"}, headers=_auth(setup["rescuer_token"]))
        assert r.status_code == 409


class TestHealthCheck:
    def test_health(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
