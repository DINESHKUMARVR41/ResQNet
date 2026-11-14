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


def test_demo_accounts_login_with_valid_role_tokens_and_dashboards(client):
    from app.core.security import decode_access_token

    demo_accounts = [
        ("citizen@resqnet.demo", "citizen"),
        ("rescuer@resqnet.demo", "rescuer"),
        ("ngo@resqnet.demo", "coordinator"),
        ("coordinator@resqnet.demo", "coordinator"),
        ("admin@resqnet.demo", "admin"),
    ]
    for email, expected_role in demo_accounts:
        response = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "ResQNetDemo!2026",
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["user"]["role"] == expected_role
        token = data["access_token"]
        assert decode_access_token(token)["role"] == expected_role
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == email
        assert client.get("/api/v1/dashboard/summary", headers=headers).json()["role"] == expected_role


def test_demo_account_seeding_is_repeatable(client):
    from sqlalchemy import func, select
    from app.core.database import SessionLocal
    from app.models.entities import User
    from app.services.seed import seed_demo_data

    demo_emails = [
        "citizen@resqnet.demo",
        "rescuer@resqnet.demo",
        "ngo@resqnet.demo",
        "coordinator@resqnet.demo",
        "admin@resqnet.demo",
    ]
    with SessionLocal() as db:
        missing_ngo = db.scalar(select(User).where(User.email == "ngo@resqnet.demo"))
        db.delete(missing_ngo)
        db.commit()
        seed_demo_data(db)
        seed_demo_data(db)
        count = db.scalar(select(func.count(User.id)).where(User.email.in_(demo_emails)))
    assert count == len(demo_emails)


def test_demo_invalid_credentials_and_role_access(client):
    invalid = client.post("/api/v1/auth/login", json={
        "email": "citizen@resqnet.demo",
        "password": "incorrect",
    })
    assert invalid.status_code == 401

    citizen = client.post("/api/v1/auth/login", json={
        "email": "citizen@resqnet.demo",
        "password": "ResQNetDemo!2026",
    }).json()
    denied = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {citizen['access_token']}"},
    )
    assert denied.status_code == 403


def test_cors_allows_vite_origins_without_credentials(client):
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in response.headers
