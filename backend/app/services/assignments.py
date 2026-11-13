"""Deterministic responder eligibility, ranking and persistent offer escalation."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.entities import (Case, User, UserRole, ResponderProfile, ResponderSkill,
    Availability, AssignmentOffer, CaseEvent, CaseHandoff)

OFFER_MINUTES = 2
ACTIVE_CASE_STATUSES = ("ASSIGNED", "IN_PROGRESS", "ON_SCENE")

def utcnow():
    return datetime.now(timezone.utc)

def distance_km(a_lat, a_lon, b_lat, b_lon):
    from math import radians, sin, cos, asin, sqrt
    p1, p2 = radians(a_lat), radians(b_lat)
    dp, dl = radians(b_lat-a_lat), radians(b_lon-a_lon)
    h = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return 6371 * 2 * asin(sqrt(min(1, h)))

def eligible_responders(db: Session, case: Case):
    profiles = db.scalars(select(ResponderProfile).join(User).join(Availability)
        .where(User.role == UserRole.RESCUER, User.is_active.is_(True), User.is_verified.is_(True),
               ResponderProfile.verified_at.is_not(None), Availability.is_available.is_(True))).all()
    offered_ids = set(db.scalars(select(AssignmentOffer.responder_id).where(AssignmentOffer.case_id == case.id)).all())
    results = []
    for profile in profiles:
        if profile.id in offered_ids:
            continue
        species = {x.lower() for x in db.scalars(select(ResponderSkill.species).where(ResponderSkill.responder_id == profile.id)).all()}
        animal = case.animal_category.lower()
        if "all" not in species and animal not in species:
            continue
        active_count = db.scalar(select(func.count(AssignmentOffer.id)).join(Case, Case.id == AssignmentOffer.case_id)
            .where(AssignmentOffer.responder_id == profile.id, AssignmentOffer.status == "ACCEPTED", Case.status.in_(ACTIVE_CASE_STATUSES))) or 0
        if active_count >= profile.capacity:
            continue
        distance = None
        if case.latitude is not None and case.longitude is not None:
            if profile.latitude is None or profile.longitude is None:
                continue
            distance = distance_km(case.latitude, case.longitude, profile.latitude, profile.longitude)
            if distance > profile.service_radius_km:
                continue
        user = db.get(User, profile.user_id)
        # Explainable score: proximity is the only ranking factor after hard eligibility.
        score = round(100 - (distance or 0) * 2, 2) if distance is not None else 50.0
        results.append({"profile": profile, "user": user, "distance_km": round(distance, 2) if distance is not None else None, "score": score})
    return sorted(results, key=lambda x: (-x["score"], x["user"].full_name.lower()))

def issue_next_offer(db: Session, case: Case, actor_id: str | None = None):
    candidates = eligible_responders(db, case)
    if not candidates:
        previous = case.status
        case.status = "NEEDS_COORDINATOR"
        db.add(CaseEvent(case_id=case.id, actor_id=actor_id, event_type="ASSIGNMENT_EXHAUSTED", from_status=previous, to_status=case.status,
            message="No eligible responder remains. Coordinator action is required; the case stays open."))
        db.commit()
        return None
    candidate = candidates[0]
    prior_count = db.scalar(select(func.count(AssignmentOffer.id)).where(AssignmentOffer.case_id == case.id)) or 0
    offer = AssignmentOffer(case_id=case.id, responder_id=candidate["profile"].id, attempt_no=prior_count+1,
        status="PENDING", score=candidate["score"], distance_km=candidate["distance_km"],
        deadline_at=utcnow()+timedelta(minutes=OFFER_MINUTES))
    previous = case.status
    case.status = "ASSIGNMENT_PENDING"
    db.add(offer); db.flush()
    db.add(CaseEvent(case_id=case.id, actor_id=actor_id, event_type="ASSIGNMENT_OFFERED", from_status=previous, to_status=case.status,
        message=f"Assignment offer #{offer.attempt_no} sent to {candidate['user'].full_name}; response due in {OFFER_MINUTES} minutes."))
    db.commit(); db.refresh(offer)
    return offer

def process_expired_offers(db: Session):
    now = utcnow()
    expired = db.scalars(select(AssignmentOffer).where(AssignmentOffer.status == "PENDING", AssignmentOffer.deadline_at <= now).with_for_update()).all()
    processed = 0
    for offer in expired:
        # SQLite ignores FOR UPDATE; status check and commit keep this idempotent in the single-worker demo.
        if offer.status != "PENDING":
            continue
        offer.status = "EXPIRED"; offer.responded_at = now; offer.response_reason = "No response before the acknowledgement deadline."
        case = db.get(Case, offer.case_id)
        if case and case.status == "ASSIGNMENT_PENDING":
            db.add(CaseEvent(case_id=case.id, event_type="OFFER_EXPIRED", from_status=case.status,
                message=f"Responder acknowledgement deadline expired for offer #{offer.attempt_no}; escalation initiated."))
            db.flush()
            issue_next_offer(db, case)
        else:
            db.commit()
        processed += 1
    pending_handoffs = db.scalars(select(CaseHandoff).where(CaseHandoff.status == "PENDING", CaseHandoff.deadline_at <= now)).all()
    for handoff in pending_handoffs:
        handoff.status = "EXPIRED"; handoff.responded_at = now
        db.add(CaseEvent(case_id=handoff.case_id, event_type="HANDOFF_EXPIRED", message="Organization handoff was not accepted before its deadline. Existing ownership remains unchanged."))
        processed += 1
    if pending_handoffs: db.commit()
    return processed
