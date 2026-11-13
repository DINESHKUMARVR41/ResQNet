from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.entities import User, UserRole, Organization, ResponderProfile, ResponderSkill, Availability

def seed_demo_data(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)): return
    org = Organization(name="Salem Animal Welfare Network (DEMO)", organization_type="ngo", city="Salem", state="Tamil Nadu", is_verified=True)
    db.add(org); db.flush()
    demo = [
        ("Demo Citizen", "citizen@resqnet.demo", UserRole.CITIZEN),
        ("Demo Responder", "rescuer@resqnet.demo", UserRole.RESCUER),
        ("Demo Coordinator", "coordinator@resqnet.demo", UserRole.COORDINATOR),
        ("Demo Administrator", "admin@resqnet.demo", UserRole.ADMIN),
    ]
    for name, email, role in demo:
        user = User(full_name=name, email=email, password_hash=hash_password("ResQNetDemo!2026"), role=role, is_active=True, is_verified=True, organization_id=org.id if role == UserRole.COORDINATOR else None)
        db.add(user); db.flush()
        if role == UserRole.RESCUER:
            profile = ResponderProfile(user_id=user.id, organization_id=org.id, service_radius_km=20, capacity=2, latitude=11.6643, longitude=78.1460, verified_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
            db.add(profile); db.flush()
            db.add_all([ResponderSkill(responder_id=profile.id, species="dog"), ResponderSkill(responder_id=profile.id, species="cat"), Availability(responder_id=profile.id, is_available=True)])
    db.commit()
