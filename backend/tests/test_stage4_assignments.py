from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.entities import Case, AssignmentOffer, User, Organization, CaseHandoff


def login(client, email):
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': 'ResQNetDemo!2026'})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def create_triaged_case(client):
    citizen = login(client, 'citizen@resqnet.demo')
    case = client.post('/api/v1/cases', headers=citizen, json={
        'animal_category': 'Dog', 'description': 'Dog hit by a vehicle, visible bleeding near Salem bus stand',
        'latitude': 11.6643, 'longitude': 78.1460
    })
    assert case.status_code == 201, case.text
    coord = login(client, 'coordinator@resqnet.demo')
    triaged = client.patch(f"/api/v1/cases/{case.json()['public_id']}/triage", headers=coord,
        json={'priority': 'CRITICAL', 'reason': 'Visible bleeding and road collision reported by caller.'})
    assert triaged.status_code == 200, triaged.text
    return case.json()['public_id'], citizen, coord


def test_matching_offer_acceptance_and_responder_case_access(client):
    public_id, _, coord = create_triaged_case(client)
    eligible = client.get(f'/api/v1/coordinator/cases/{public_id}/eligible-responders', headers=coord)
    assert eligible.status_code == 200 and eligible.json()[0]['name'] == 'Demo Responder'
    assigned = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord)
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()['status'] == 'PENDING'
    responder = login(client, 'rescuer@resqnet.demo')
    offers = client.get('/api/v1/responder/offers', headers=responder).json()
    assert any(x['case_id'] == public_id and x['status'] == 'PENDING' for x in offers)
    assert client.get(f'/api/v1/cases/{public_id}', headers=responder).status_code == 200
    accepted = client.post(f"/api/v1/responder/offers/{assigned.json()['offer_id']}/accept", headers=responder)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'ACCEPTED'
    assert client.get(f'/api/v1/cases/{public_id}', headers=responder).json()['status'] == 'ASSIGNED'
    duplicate = client.post(f"/api/v1/responder/offers/{assigned.json()['offer_id']}/accept", headers=responder)
    assert duplicate.status_code == 409


def test_decline_exhausts_candidates_and_returns_case_to_coordinator(client):
    public_id, _, coord = create_triaged_case(client)
    assigned = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord).json()
    responder = login(client, 'rescuer@resqnet.demo')
    declined = client.post(f"/api/v1/responder/offers/{assigned['offer_id']}/decline", headers=responder,
        json={'reason': 'Outside my available operating hours today.'})
    assert declined.status_code == 200, declined.text
    assert declined.json()['status'] == 'NEEDS_COORDINATOR'
    assert client.get(f'/api/v1/cases/{public_id}', headers=coord).json()['status'] == 'NEEDS_COORDINATOR'


def test_expired_offer_is_persistently_escalated(client):
    public_id, _, coord = create_triaged_case(client)
    assigned = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord).json()
    with SessionLocal() as db:
        offer = db.get(AssignmentOffer, assigned['offer_id'])
        from datetime import datetime, timedelta, timezone
        offer.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    admin = login(client, 'admin@resqnet.demo')
    result = client.post('/api/v1/jobs/process-deadlines', headers=admin)
    assert result.status_code == 200, result.text
    assert result.json()['expired_offers_processed'] >= 1
    assert client.get(f'/api/v1/cases/{public_id}', headers=coord).json()['status'] == 'NEEDS_COORDINATOR'


def test_handoff_requires_explicit_acceptance_before_ownership_changes(client):
    public_id, _, coord = create_triaged_case(client)
    assigned = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord).json()
    responder = login(client, 'rescuer@resqnet.demo')
    client.post(f"/api/v1/responder/offers/{assigned['offer_id']}/accept", headers=responder)
    with SessionLocal() as db:
        org = Organization(name='Verified Partner NGO', organization_type='ngo', city='Salem', state='Tamil Nadu', is_verified=True)
        db.add(org); db.flush()
        from app.core.security import hash_password
        receiver = User(full_name='Partner Coordinator', email='partner@resqnet.demo', password_hash=hash_password('ResQNetDemo!2026'), role='coordinator', is_active=True, is_verified=True, organization_id=org.id)
        db.add(receiver); db.commit(); org_id=org.id; receiver_id=receiver.id
    request = client.post(f'/api/v1/coordinator/cases/{public_id}/handoffs', headers=coord,
        json={'to_organization_id': org_id, 'reason': 'Partner NGO has specialist animal transport capability.'})
    assert request.status_code == 201, request.text
    with SessionLocal() as db:
        case = db.scalar(select(Case).where(Case.public_id == public_id))
        assert case.owner_organization_id is not None
        assert case.owner_organization_id != org_id
    receiver_token = client.post('/api/v1/auth/login', json={'email':'partner@resqnet.demo','password':'ResQNetDemo!2026'}).json()['access_token']
    accepted = client.post(f"/api/v1/coordinator/handoffs/{request.json()['handoff_id']}/accept", headers={'Authorization':f'Bearer {receiver_token}'})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['owner_organization_id'] == org_id


def test_responder_progress_is_sequential_and_requires_accepted_assignment(client):
    public_id, _, coord = create_triaged_case(client)
    assigned = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord).json()
    responder = login(client, 'rescuer@resqnet.demo')
    denied = client.patch(f'/api/v1/responder/cases/{public_id}/status', headers=responder, json={'status':'ON_SCENE'})
    assert denied.status_code == 404
    client.post(f"/api/v1/responder/offers/{assigned['offer_id']}/accept", headers=responder)
    started = client.patch(f'/api/v1/responder/cases/{public_id}/status', headers=responder, json={'status':'IN_PROGRESS'})
    assert started.status_code == 200 and started.json()['status'] == 'IN_PROGRESS'
    arrived = client.patch(f'/api/v1/responder/cases/{public_id}/status', headers=responder, json={'status':'ON_SCENE'})
    assert arrived.status_code == 200 and arrived.json()['status'] == 'ON_SCENE'


def test_decline_automatically_offers_next_eligible_responder(client):
    from datetime import datetime, timezone
    from app.core.security import hash_password
    from app.models.entities import ResponderProfile, ResponderSkill, Availability, User, UserRole, Organization
    with SessionLocal() as db:
        org = db.scalar(select(Organization).where(Organization.name == 'Salem Animal Welfare Network (DEMO)'))
        user = User(full_name='Second Responder', email='second.responder@resqnet.demo', password_hash=hash_password('ResQNetDemo!2026'),
                    role=UserRole.RESCUER, is_active=True, is_verified=True)
        db.add(user); db.flush()
        profile = ResponderProfile(user_id=user.id, organization_id=org.id, service_radius_km=20, capacity=2,
                                   latitude=11.6650, longitude=78.1460, verified_at=datetime.now(timezone.utc))
        db.add(profile); db.flush()
        db.add_all([ResponderSkill(responder_id=profile.id, species='dog'), Availability(responder_id=profile.id, is_available=True)])
        db.commit()
    public_id, _, coord = create_triaged_case(client)
    first = client.post(f'/api/v1/coordinator/cases/{public_id}/assign', headers=coord).json()
    responder = login(client, 'rescuer@resqnet.demo')
    declined = client.post(f"/api/v1/responder/offers/{first['offer_id']}/decline", headers=responder,
                           json={'reason':'Unable to attend this incident.'})
    assert declined.status_code == 200, declined.text
    assert declined.json()['status'] == 'DECLINED'
    assert declined.json()['next_responder'] == 'Second Responder'
    offers = client.get('/api/v1/responder/offers', headers=login(client, 'second.responder@resqnet.demo')).json()
    assert any(x['case_id'] == public_id and x['status'] == 'PENDING' for x in offers)
