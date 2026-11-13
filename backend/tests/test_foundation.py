def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_register_login_and_me(client):
    payload = {"full_name": "Test Citizen", "email": "test@example.com", "password": "StrongPass!2026", "role": "citizen"}
    created = client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 201, created.text
    token = created.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "test@example.com"
    logged_in = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "StrongPass!2026"})
    assert logged_in.status_code == 200

def test_public_cannot_register_admin(client):
    payload = {"full_name": "Bad Actor", "email": "bad@example.com", "password": "StrongPass!2026", "role": "admin"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 400

def test_role_access_is_enforced(client):
    payload = {"full_name": "Test Citizen", "email": "citizen@example.com", "password": "StrongPass!2026", "role": "citizen"}
    token = client.post("/api/v1/auth/register", json=payload).json()["access_token"]
    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_protected_route_requires_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_duplicate_email_is_rejected(client):
    payload = {"full_name": "Test Citizen", "email": "duplicate@example.com", "password": "StrongPass!2026", "role": "citizen"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
