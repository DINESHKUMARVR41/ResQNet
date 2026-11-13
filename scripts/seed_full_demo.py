"""Comprehensive Salem demo seed script for ResQNet Stages 5-8."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.models.entities import (
    User, UserRole, Organization, ResponderProfile, ResponderSkill,
    Availability, Case, CaseEvent, AssignmentOffer, CaseHandoff,
    RescueEvidence, ResponderReliabilityScore, Notification, new_id, utcnow,
)

# Ensure tables exist
Base.metadata.create_all(bind=engine)

PASSWORD = hash_password("Demo1234!")
NOW = utcnow()


def seed():
    db = SessionLocal()
    try:
        # ---- Organizations ----
        org1 = db.scalar(select(Organization).where(Organization.name == "PawsForward Animal Welfare"))
        if not org1:
            org1 = Organization(name="PawsForward Animal Welfare", organization_type="ngo",
                                city="Salem", state="Tamil Nadu", is_verified=True)
            db.add(org1); db.flush()
            print("[+] Created org: PawsForward Animal Welfare")
        else:
            print("[=] Exists: PawsForward Animal Welfare")

        org2 = db.scalar(select(Organization).where(Organization.name == "Samaritans Animal Trust"))
        if not org2:
            org2 = Organization(name="Samaritans Animal Trust", organization_type="ngo",
                                city="Salem", state="Tamil Nadu", is_verified=True)
            db.add(org2); db.flush()
            print("[+] Created org: Samaritans Animal Trust")
        else:
            print("[=] Exists: Samaritans Animal Trust")

        # ---- Users ----
        users_spec = [
            ("Rajesh Kumar", "citizen@resqnet.demo", UserRole.CITIZEN, None),
            ("Priya Sundaram", "citizen2@resqnet.demo", UserRole.CITIZEN, None),
            ("Karthik Velan", "rescuer@resqnet.demo", UserRole.RESCUER, org1.id),
            ("Senthil Kumar", "rescuer2@resqnet.demo", UserRole.RESCUER, org2.id),
            ("Lakshmi Devi", "coordinator@resqnet.demo", UserRole.COORDINATOR, org1.id),
            ("Arun Prasad", "coordinator2@resqnet.demo", UserRole.COORDINATOR, org2.id),
            ("Admin Supervisor", "admin@resqnet.demo", UserRole.ADMIN, None),
        ]
        user_map = {}
        for full_name, email, role, org_id in users_spec:
            u = db.scalar(select(User).where(User.email == email))
            if not u:
                u = User(full_name=full_name, email=email, password_hash=PASSWORD,
                         role=role, is_active=True, is_verified=True, organization_id=org_id)
                db.add(u); db.flush()
                print(f"[+] Created user: {email} ({role.value})")
            else:
                u.password_hash = PASSWORD
                u.role = role
                u.is_active = True
                u.is_verified = True
                u.organization_id = org_id
                print(f"[=] Updated user: {email}")
            user_map[email] = u

        # ---- Responder Profiles ----
        rescuer_configs = [
            ("rescuer@resqnet.demo", org1.id, 11.6643, 78.1460, 20.0, 3,
             ["dog", "cat", "bird", "all"]),
            ("rescuer2@resqnet.demo", org2.id, 11.6700, 78.1500, 25.0, 2,
             ["all"]),
        ]
        profile_map = {}
        for email, org_id, lat, lon, radius, cap, skills in rescuer_configs:
            u = user_map[email]
            p = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == u.id))
            if not p:
                p = ResponderProfile(user_id=u.id, organization_id=org_id,
                                     latitude=lat, longitude=lon,
                                     service_radius_km=radius, capacity=cap,
                                     verified_at=NOW)
                db.add(p); db.flush()
            else:
                p.organization_id = org_id
                p.latitude = lat; p.longitude = lon
                p.service_radius_km = radius; p.capacity = cap
                p.verified_at = p.verified_at or NOW
            profile_map[email] = p

            # Skills
            existing_skills = set(db.scalars(
                select(ResponderSkill.species).where(ResponderSkill.responder_id == p.id)
            ).all())
            for s in skills:
                if s not in existing_skills:
                    db.add(ResponderSkill(responder_id=p.id, species=s))

            # Availability
            avail = db.scalar(select(Availability).where(Availability.responder_id == p.id))
            if not avail:
                db.add(Availability(responder_id=p.id, is_available=True))
            else:
                avail.is_available = True

        db.commit()

        # ---- Demo Cases ----
        cases_spec = [
            {
                "reporter": "citizen@resqnet.demo",
                "animal": "Dog", "priority": "CRITICAL", "status": "VERIFICATION_PENDING",
                "desc": "Black dog hit by an autorickshaw near Salem Junction. Cannot stand, visible bleeding on hind leg. Dog is whimpering and lying on the road shoulder.",
                "lat": 11.6643, "lon": 78.1460, "landmark": "Salem Junction Railway Station",
                "assign_rescuer": "rescuer@resqnet.demo",
                "events": ["REPORTED", "TRIAGED", "ASSIGNED", "EN_ROUTE", "ARRIVED", "RESCUE_IN_PROGRESS", "RESCUED"],
            },
            {
                "reporter": "citizen2@resqnet.demo",
                "animal": "Cat", "priority": "HIGH", "status": "ASSIGNED",
                "desc": "Small tabby cat trapped between two walls near Ammapet bus stand. Cat is crying loudly and cannot free itself. No visible injuries.",
                "lat": 11.6550, "lon": 78.1580, "landmark": "Ammapet Bus Stand",
                "assign_rescuer": "rescuer@resqnet.demo",
                "events": ["REPORTED", "TRIAGED", "ASSIGNED"],
            },
            {
                "reporter": "citizen@resqnet.demo",
                "animal": "Cow", "priority": "CRITICAL", "status": "VERIFIED",
                "desc": "Cow collapsed on Omalur Road near the sugar factory. Appears severely dehydrated and unable to stand. Vehicle traffic is a hazard.",
                "lat": 11.6400, "lon": 78.1200, "landmark": "Omalur Road Sugar Factory",
                "assign_rescuer": "rescuer2@resqnet.demo",
                "events": ["REPORTED", "TRIAGED", "ASSIGNED", "EN_ROUTE", "ARRIVED", "RESCUE_IN_PROGRESS", "RESCUED", "VERIFIED"],
            },
            {
                "reporter": "citizen2@resqnet.demo",
                "animal": "Bird", "priority": "MEDIUM", "status": "TRIAGED",
                "desc": "Injured pigeon found in the park near Five Roads. Wing appears broken. Bird is alive but cannot fly.",
                "lat": 11.6700, "lon": 78.1550, "landmark": "Five Roads Park",
                "events": ["REPORTED", "TRIAGED"],
            },
            {
                "reporter": "citizen@resqnet.demo",
                "animal": "Dog", "priority": "HIGH", "status": "NEEDS_COORDINATOR",
                "desc": "Two stray puppies found abandoned in a cardboard box near Fairlands. They appear weak and malnourished. Box is near a busy road.",
                "lat": 11.6800, "lon": 78.1350, "landmark": "Fairlands Main Road",
                "events": ["REPORTED", "TRIAGED", "NEEDS_COORDINATOR"],
            },
            {
                "reporter": "citizen2@resqnet.demo",
                "animal": "Monkey", "priority": "LOW", "status": "REPORTED",
                "desc": "A monkey has been sitting on a wall near residential area for 2 days. It appears lethargic and not moving much. No visible injury.",
                "lat": 11.6580, "lon": 78.1420, "landmark": "Shevapet Residential Area",
                "events": ["REPORTED"],
            },
            {
                "reporter": "citizen@resqnet.demo",
                "animal": "Dog", "priority": "HIGH", "status": "CLOSED",
                "desc": "Injured stray dog near steel plant area. Limping and has a wound on its side.",
                "lat": 11.6500, "lon": 78.1600, "landmark": "Salem Steel Plant Gate",
                "assign_rescuer": "rescuer2@resqnet.demo",
                "events": ["REPORTED", "TRIAGED", "ASSIGNED", "EN_ROUTE", "ARRIVED", "RESCUE_IN_PROGRESS", "RESCUED", "VERIFIED", "CLOSED"],
            },
        ]

        for i, spec in enumerate(cases_spec):
            reporter = user_map[spec["reporter"]]
            public_id = f"RQ-DEMO-{i+1:03d}"

            existing = db.scalar(select(Case).where(Case.public_id == public_id))
            if existing:
                print(f"[=] Case {public_id} exists")
                continue

            case = Case(
                public_id=public_id, reporter_id=reporter.id,
                animal_category=spec["animal"], description=spec["desc"],
                status=spec["status"], priority=spec["priority"],
                latitude=spec["lat"], longitude=spec["lon"],
                landmark=spec.get("landmark"),
                ai_summary=spec["desc"][:300],
                triage_reason=f"Demo case with {spec['priority']} priority.",
                triage_confidence=0.85, needs_human_review=False,
                created_at=NOW - timedelta(hours=24-i*3),
            )
            db.add(case); db.flush()

            # Events
            status_map = {
                "REPORTED": "REPORT_SUBMITTED",
                "TRIAGED": "TRIAGE_REVIEWED",
                "ASSIGNED": "ASSIGNMENT_ACCEPTED",
                "EN_ROUTE": "STATUS_EN_ROUTE",
                "ARRIVED": "STATUS_ARRIVED",
                "RESCUE_IN_PROGRESS": "STATUS_RESCUE_IN_PROGRESS",
                "RESCUED": "STATUS_VERIFICATION_PENDING",
                "VERIFICATION_PENDING": "VERIFICATION_REQUESTED",
                "VERIFIED": "RESCUE_VERIFIED",
                "CLOSED": "CASE_CLOSED",
                "NEEDS_COORDINATOR": "ASSIGNMENT_EXHAUSTED",
            }
            prev = None
            for j, status in enumerate(spec["events"]):
                db.add(CaseEvent(
                    case_id=case.id,
                    actor_id=reporter.id,
                    event_type=status_map.get(status, f"STATUS_{status}"),
                    from_status=prev, to_status=status,
                    message=f"Demo event: {status.replace('_', ' ').title()}",
                    created_at=case.created_at + timedelta(minutes=j*10),
                ))
                prev = status

            # Assignment
            if spec.get("assign_rescuer"):
                rescuer_user = user_map[spec["assign_rescuer"]]
                profile = profile_map[spec["assign_rescuer"]]
                offer = AssignmentOffer(
                    case_id=case.id, responder_id=profile.id,
                    attempt_no=1, status="ACCEPTED", score=85.0,
                    distance_km=2.5, offered_at=case.created_at + timedelta(minutes=5),
                    deadline_at=case.created_at + timedelta(minutes=7),
                    responded_at=case.created_at + timedelta(minutes=6),
                )
                db.add(offer)

            print(f"[+] Created case: {public_id} ({spec['animal']}, {spec['status']})")

        db.commit()

        # ---- Notifications for demo ----
        coord1 = user_map["coordinator@resqnet.demo"]
        citizen1 = user_map["citizen@resqnet.demo"]
        existing_notifs = db.scalar(select(Notification).where(Notification.user_id == coord1.id))
        if not existing_notifs:
            notif_specs = [
                (coord1.id, "CASE_CREATED", "New emergency report", "A critical case involving a dog near Salem Junction has been submitted."),
                (coord1.id, "ASSIGNMENT_ACCEPTED", "Responder accepted", "Karthik Velan has accepted the assignment for case RQ-DEMO-001."),
                (coord1.id, "EVIDENCE_SUBMITTED", "Evidence received", "Rescue evidence has been submitted for case RQ-DEMO-001."),
                (citizen1.id, "RESCUE_VERIFIED", "Your case was verified", "Case RQ-DEMO-003 has been verified as successfully rescued."),
                (citizen1.id, "CASE_CLOSED", "Case closed", "Case RQ-DEMO-007 has been closed after successful rescue and verification."),
            ]
            for uid, etype, title, body in notif_specs:
                db.add(Notification(id=new_id(), user_id=uid, event_type=etype, title=title, body=body))
            db.commit()
            print("[+] Created demo notifications")

        print("\n" + "="*60)
        print("  ResQNet Demo Environment Ready")
        print("="*60)
        print("\n  Demo Credentials:")
        print("  " + "-"*56)
        print(f"  {'Role':<15} {'Email':<30} {'Password'}")
        print("  " + "-"*56)
        print(f"  {'Citizen':<15} {'citizen@resqnet.demo':<30} Demo1234!")
        print(f"  {'Citizen 2':<15} {'citizen2@resqnet.demo':<30} Demo1234!")
        print(f"  {'Rescuer':<15} {'rescuer@resqnet.demo':<30} Demo1234!")
        print(f"  {'Rescuer 2':<15} {'rescuer2@resqnet.demo':<30} Demo1234!")
        print(f"  {'Coordinator':<15} {'coordinator@resqnet.demo':<30} Demo1234!")
        print(f"  {'Coordinator 2':<15} {'coordinator2@resqnet.demo':<30} Demo1234!")
        print(f"  {'Admin':<15} {'admin@resqnet.demo':<30} Demo1234!")
        print("  " + "-"*56)
        print(f"\n  Organizations: PawsForward Animal Welfare, Samaritans Animal Trust")
        print(f"  Cases: 7 demo cases across various statuses")
        print(f"  Location: Salem, Tamil Nadu, India\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
