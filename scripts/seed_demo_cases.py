"""Insert two clearly synthetic Salem emergency reports for a local demo."""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("SEED_DEMO_DATA", "true")
from sqlalchemy import select
from app.core.database import SessionLocal, Base, engine
from app.models.entities import User, Case, CaseEvent
from app.services.triage import suggest_priority

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    citizen = db.scalar(select(User).where(User.email == "citizen@resqnet.demo"))
    if not citizen:
        raise SystemExit("Demo citizen missing. Start the API once with SEED_DEMO_DATA=true first.")
    if db.scalar(select(Case.id).limit(1)):
        print("Cases already exist; no demo cases inserted.")
        raise SystemExit(0)
    samples = [
        ("Dog", "SYNTHETIC DEMO: Dog reportedly struck by a vehicle near Salem New Bus Stand; visible bleeding was reported by the caller.", 11.6643, 78.1460, "Salem New Bus Stand"),
        ("Dog", "SYNTHETIC DEMO: Another citizen reports an injured dog close to Salem New Bus Stand. This is intentionally near the first report to demonstrate duplicate suggestions.", 11.6645, 78.1462, "Near Salem New Bus Stand"),
    ]
    for index, (category, description, lat, lon, landmark) in enumerate(samples, start=1):
        priority, reason, confidence, review = suggest_priority(description)
        case = Case(public_id=f"RQ-DEMO-{datetime.now(timezone.utc):%H%M%S}-{index}", reporter_id=citizen.id,
            animal_category=category, description=description, status="REPORTED", priority=priority,
            latitude=lat, longitude=lon, landmark=landmark, triage_reason=reason,
            triage_confidence=confidence, needs_human_review=review)
        db.add(case); db.flush()
        db.add(CaseEvent(case_id=case.id, actor_id=citizen.id, event_type="REPORT_SUBMITTED", to_status="REPORTED",
            message="Synthetic Salem demonstration report. Not a real animal emergency."))
    db.commit()
    print("Inserted 2 synthetic Salem reports. They are not real rescue incidents.")
