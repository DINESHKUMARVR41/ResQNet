from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import hash_password, verify_password
from app.models.entities import User, UserRole, Organization, ResponderProfile, ResponderSkill, Availability

def seed_demo_data(db: Session) -> None:
    org = db.scalar(select(Organization).where(Organization.name == "Salem Animal Welfare Network (DEMO)"))
    if not org:
        org = Organization(name="Salem Animal Welfare Network (DEMO)", organization_type="ngo", city="Salem", state="Tamil Nadu", is_verified=True)
        db.add(org); db.flush()
    demo = [
        ("Demo Citizen", "citizen@resqnet.demo", UserRole.CITIZEN),
        ("Demo Responder", "rescuer@resqnet.demo", UserRole.RESCUER),
        ("Demo NGO", "ngo@resqnet.demo", UserRole.COORDINATOR),
        ("Demo Coordinator", "coordinator@resqnet.demo", UserRole.COORDINATOR),
        ("Demo Administrator", "admin@resqnet.demo", UserRole.ADMIN),
    ]
    for name, email, role in demo:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(full_name=name, email=email, password_hash=hash_password("ResQNetDemo!2026"), role=role)
            db.add(user)
        elif not verify_password("ResQNetDemo!2026", user.password_hash):
            user.password_hash = hash_password("ResQNetDemo!2026")
        user.role = role
        user.is_active = True
        user.is_verified = True
        user.organization_id = org.id if role == UserRole.COORDINATOR else None
        db.flush()
        if role == UserRole.RESCUER:
            profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
            if not profile:
                profile = ResponderProfile(user_id=user.id)
                db.add(profile); db.flush()
            profile.organization_id = org.id
            profile.service_radius_km = 20
            profile.capacity = 2
            profile.latitude = 11.6643
            profile.longitude = 78.1460
            profile.verified_at = profile.verified_at or datetime.now(timezone.utc)
            existing_skills = set(db.scalars(select(ResponderSkill.species).where(ResponderSkill.responder_id == profile.id)).all())
            for species in ("dog", "cat"):
                if species not in existing_skills:
                    db.add(ResponderSkill(responder_id=profile.id, species=species))
            availability = db.scalar(select(Availability).where(Availability.responder_id == profile.id))
            if not availability:
                db.add(Availability(responder_id=profile.id, is_available=True))
            else:
                availability.is_available = True
    db.commit()
