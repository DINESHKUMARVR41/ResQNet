from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.entities import User, UserRole, Organization, ResponderProfile, ResponderSkill, Availability, Case
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserRead

router = APIRouter()

@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if payload.role not in (UserRole.CITIZEN, UserRole.RESCUER):
        raise HTTPException(status_code=400, detail="Public registration is limited to citizen and rescuer accounts")
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(full_name=payload.full_name.strip(), email=email, phone=payload.phone, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user); db.flush()
    if payload.role == UserRole.RESCUER:
        profile = ResponderProfile(user_id=user.id)
        db.add(profile); db.flush()
        db.add(Availability(responder_id=profile.id, is_available=False))
    db.commit(); db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id, user.role.value), user=user)

@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active: raise HTTPException(status_code=403, detail="This account is disabled")
    return TokenResponse(access_token=create_access_token(user.id, user.role.value), user=user)

@router.get("/auth/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user

@router.get("/dashboard/summary")
def dashboard_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_cases = db.scalar(select(func.count(Case.id))) or 0
    open_cases = db.scalar(select(func.count(Case.id)).where(Case.status.notin_(["CLOSED", "FLAGGED_FALSE", "DUPLICATE_MERGED"]))) or 0
    available = db.scalar(select(func.count(Availability.id)).where(Availability.is_available.is_(True))) or 0
    return {"role": user.role.value, "total_cases": total_cases, "open_cases": open_cases, "available_responders": available, "environment": settings.environment, "data_label": "Live database records"}

@router.get("/admin/users", response_model=list[UserRead])
def list_users(_: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at.desc()).limit(200)).all())

@router.get("/coordinator/organizations")
def list_organizations(_: User = Depends(require_roles(UserRole.ADMIN, UserRole.COORDINATOR)), db: Session = Depends(get_db)):
    organizations = db.scalars(select(Organization).order_by(Organization.name)).all()
    return [{"id": o.id, "name": o.name, "type": o.organization_type, "city": o.city, "state": o.state, "verified": o.is_verified} for o in organizations]

# Stage 3: citizen reporting, coordinator triage, case tracking and event history.
import json, math, os, re, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import File, UploadFile
from fastapi.responses import FileResponse
from app.models.entities import CaseEvent
from app.schemas.cases import CaseCreate, CaseRead, TriageUpdate, CaseEventRead
from app.services.triage import suggest_priority

UPLOAD_DIR = Path(os.getenv("RESQNET_UPLOAD_DIR", "uploads")).resolve()
ALLOWED_PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024

def _distance_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * radius * math.asin(math.sqrt(a))

def _duplicates(db: Session, case: Case):
    if case.latitude is None or case.longitude is None:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    candidates = db.scalars(select(Case).where(
        Case.id != case.id,
        Case.animal_category == case.animal_category,
        Case.created_at >= cutoff,
        Case.latitude.is_not(None), Case.longitude.is_not(None)
    ).order_by(Case.created_at.desc()).limit(100)).all()
    matches = []
    for other in candidates:
        distance = _distance_km(case.latitude, case.longitude, other.latitude, other.longitude)
        if distance <= 1.0:
            # Compute word-overlap similarity score
            words_a = set(re.sub(r"[^\w\s]", "", case.description.lower()).split())
            words_b = set(re.sub(r"[^\w\s]", "", other.description.lower()).split())
            union = words_a | words_b
            similarity_score = round(len(words_a & words_b) / len(union), 3) if union else 0.0
            matches.append({"public_id": other.public_id, "distance_km": round(distance, 2), "status": other.status, "created_at": other.created_at.isoformat(), "description": other.description[:180], "similarity_score": similarity_score})
    return matches[:5]

def _case_read(db: Session, case: Case, include_events: bool = True):
    actor_names = {u.id: u.full_name for u in db.scalars(select(User)).all()} if include_events else {}
    events = db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.created_at.asc())).all() if include_events else []
    return {
        "id": case.id, "public_id": case.public_id, "reporter_id": case.reporter_id,
        "animal_category": case.animal_category, "description": case.description,
        "status": case.status, "priority": case.priority, "latitude": case.latitude,
        "longitude": case.longitude, "landmark": case.landmark, "address_text": case.address_text,
        "reporter_phone": case.reporter_phone, "ai_summary": case.ai_summary,
        "triage_reason": case.triage_reason, "triage_confidence": case.triage_confidence,
        "needs_human_review": case.needs_human_review, "has_photo": bool(case.photo_path),
        "created_at": case.created_at, "updated_at": case.updated_at,
        "possible_duplicates": _duplicates(db, case),
        "events": [{"id": e.id, "event_type": e.event_type, "from_status": e.from_status,
            "to_status": e.to_status, "message": e.message, "created_at": e.created_at,
            "actor_name": actor_names.get(e.actor_id) if e.actor_id else "System"} for e in events]
    }

@router.post("/cases", response_model=CaseRead, status_code=201)
def create_case(payload: CaseCreate, user: User = Depends(require_roles(UserRole.CITIZEN)), db: Session = Depends(get_db)):
    priority, reason, confidence, review = suggest_priority(payload.description)
    case = Case(
        public_id=f"RQ-{datetime.now(timezone.utc):%y%m%d}-{uuid.uuid4().hex[:6].upper()}",
        reporter_id=user.id, animal_category=payload.animal_category.strip(),
        description=payload.description.strip(), status="REPORTED", priority=priority,
        latitude=payload.latitude, longitude=payload.longitude,
        landmark=payload.landmark.strip() if payload.landmark else None,
        address_text=payload.address_text.strip() if payload.address_text else None,
        reporter_phone=payload.reporter_phone or user.phone,
        ai_summary=payload.description.strip()[:500], triage_reason=reason,
        triage_confidence=confidence, needs_human_review=review,
    )
    db.add(case); db.flush()
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="REPORT_SUBMITTED", to_status="REPORTED", message="Emergency report submitted by citizen."))
    db.commit(); db.refresh(case)
    return _case_read(db, case)

@router.get("/cases", response_model=list[CaseRead])
def list_cases(user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    query = select(Case).order_by(Case.created_at.desc()).offset(offset).limit(limit)
    if user.role == UserRole.CITIZEN:
        query = query.where(Case.reporter_id == user.id)
    elif user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        if not profile: return []
        case_ids = select(AssignmentOffer.case_id).where(AssignmentOffer.responder_id == profile.id, AssignmentOffer.status.in_(["PENDING", "ACCEPTED"]))
        query = query.where(Case.id.in_(case_ids))
    elif user.role not in (UserRole.COORDINATOR, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Not permitted to view cases")
    cases = db.scalars(query).all()
    return [_case_read(db, c, include_events=False) for c in cases]

@router.get("/cases/{public_id}", response_model=CaseRead)
def get_case(public_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.CITIZEN and case.reporter_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        allowed = profile and db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id,
            AssignmentOffer.responder_id == profile.id, AssignmentOffer.status.in_(["PENDING", "ACCEPTED"])))
        if not allowed: raise HTTPException(status_code=404, detail="Case not found")
    return _case_read(db, case)

@router.patch("/cases/{public_id}/triage", response_model=CaseRead)
def update_case_triage(public_id: str, payload: TriageUpdate, user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("REPORTED", "TRIAGED"):
        raise HTTPException(status_code=409, detail="Triage can only be changed before assignment")
    previous = case.status
    case.priority = payload.priority
    case.triage_reason = f"Coordinator override by {user.full_name}: {payload.reason.strip()}"
    case.needs_human_review = False
    if case.status == "REPORTED": case.status = "TRIAGED"
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="TRIAGE_REVIEWED", from_status=previous, to_status=case.status, message=f"Priority set to {case.priority}. Reason: {payload.reason.strip()}"))
    db.commit(); db.refresh(case)
    return _case_read(db, case)

@router.post("/cases/{public_id}/photo", status_code=201)
async def upload_case_photo(public_id: str, photo: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.CITIZEN and case.reporter_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role not in (UserRole.CITIZEN, UserRole.COORDINATOR, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Not permitted to upload evidence for this case")
    extension = ALLOWED_PHOTO_TYPES.get(photo.content_type or "")
    if not extension: raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP images are accepted")
    content = await photo.read(MAX_PHOTO_BYTES + 1)
    if not content or len(content) > MAX_PHOTO_BYTES: raise HTTPException(status_code=413, detail="Image must be between 1 byte and 5 MB")
    valid = (extension == ".jpg" and content.startswith(b"\xff\xd8\xff")) or (extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or (extension == ".webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP")
    if not valid: raise HTTPException(status_code=415, detail="Image content does not match its declared type")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{case.id}-{uuid.uuid4().hex}{extension}"
    target = UPLOAD_DIR / filename
    target.write_bytes(content)
    case.photo_path = str(target); case.photo_content_type = photo.content_type
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="PHOTO_UPLOADED", message="A report photograph was securely uploaded."))
    db.commit()
    return {"message": "Photo uploaded", "has_photo": True}


@router.get("/cases/{public_id}/photo")
def get_case_photo(public_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.CITIZEN and case.reporter_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        allowed = profile and db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id,
            AssignmentOffer.responder_id == profile.id, AssignmentOffer.status == "ACCEPTED"))
        if not allowed: raise HTTPException(status_code=403, detail="Photo access requires an accepted assignment")
    if not case.photo_path or not Path(case.photo_path).is_file():
        raise HTTPException(status_code=404, detail="No photograph is available")
    return FileResponse(case.photo_path, media_type=case.photo_content_type or "application/octet-stream", filename=Path(case.photo_path).name)

# Stage 4: verified responder matching, acknowledgement offers and deadline escalation.
from app.models.entities import AssignmentOffer, CaseHandoff
from app.schemas.assignments import ResponderProfileUpdate, AvailabilityUpdate, OfferResponse
from app.services.assignments import eligible_responders, issue_next_offer, process_expired_offers, utcnow

@router.get("/responders/me/profile")
def get_responder_profile(user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile: raise HTTPException(status_code=404, detail="Responder profile not found")
    availability = db.scalar(select(Availability).where(Availability.responder_id == profile.id))
    skills = db.scalars(select(ResponderSkill.species).where(ResponderSkill.responder_id == profile.id)).all()
    return {"verified": profile.verified_at is not None and user.is_verified, "species": list(skills), "service_radius_km": profile.service_radius_km,
        "latitude": profile.latitude, "longitude": profile.longitude, "capacity": profile.capacity,
        "is_available": bool(availability and availability.is_available)}

@router.put("/responders/me/profile")
def update_responder_profile(payload: ResponderProfileUpdate, user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile: raise HTTPException(status_code=404, detail="Responder profile not found")
    profile.service_radius_km = payload.service_radius_km; profile.latitude = payload.latitude
    profile.longitude = payload.longitude; profile.capacity = payload.capacity
    db.query(ResponderSkill).filter(ResponderSkill.responder_id == profile.id).delete()
    for species in payload.species:
        value = species.strip().lower()
        if value: db.add(ResponderSkill(responder_id=profile.id, species=value))
    db.commit()
    return get_responder_profile(user, db)

@router.patch("/responders/me/availability")
def set_responder_availability(payload: AvailabilityUpdate, user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile: raise HTTPException(status_code=404, detail="Responder profile not found")
    if payload.is_available and (not user.is_verified or profile.verified_at is None):
        raise HTTPException(status_code=403, detail="Your responder account must be verified before going available")
    availability = db.scalar(select(Availability).where(Availability.responder_id == profile.id))
    if not availability:
        availability = Availability(responder_id=profile.id); db.add(availability)
    availability.is_available = payload.is_available; db.commit()
    return {"is_available": availability.is_available}

@router.patch("/admin/responders/{user_id}/verify")
def verify_responder(user_id: str, admin: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    responder = db.get(User, user_id)
    if not responder or responder.role != UserRole.RESCUER: raise HTTPException(status_code=404, detail="Responder not found")
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == responder.id))
    if not profile: raise HTTPException(status_code=404, detail="Responder profile not found")
    responder.is_verified = True; profile.verified_at = utcnow(); db.commit()
    return {"verified": True, "responder_id": responder.id}

@router.get("/coordinator/cases/{public_id}/eligible-responders")
def get_eligible_responders(public_id: str, _: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    return [{"responder_id": x["user"].id, "name": x["user"].full_name, "organization_id": x["profile"].organization_id,
        "distance_km": x["distance_km"], "score": x["score"], "service_radius_km": x["profile"].service_radius_km,
        "capacity": x["profile"].capacity} for x in eligible_responders(db, case)]

@router.post("/coordinator/cases/{public_id}/assign", status_code=201)
def assign_case(public_id: str, coordinator: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("TRIAGED", "NEEDS_COORDINATOR"):
        raise HTTPException(status_code=409, detail=f"Case must be TRIAGED before assignment (current: {case.status})")
    if db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id, AssignmentOffer.status == "PENDING")):
        raise HTTPException(status_code=409, detail="A pending assignment offer already exists")
    offer = issue_next_offer(db, case, coordinator.id)
    if not offer: return {"status": "NEEDS_COORDINATOR", "message": "No eligible responders. Review service area, skills, verification and availability."}
    profile = db.get(ResponderProfile, offer.responder_id); responder = db.get(User, profile.user_id)
    return {"offer_id": offer.id, "case_id": case.public_id, "responder_name": responder.full_name, "status": offer.status,
        "attempt_no": offer.attempt_no, "deadline_at": offer.deadline_at.isoformat(), "distance_km": offer.distance_km}

@router.get("/responder/offers")
def responder_offers(user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile: return []
    offers = db.scalars(select(AssignmentOffer).where(AssignmentOffer.responder_id == profile.id).order_by(AssignmentOffer.offered_at.desc()).limit(100)).all()
    return [{"offer_id": o.id, "case_id": db.get(Case, o.case_id).public_id, "animal_category": db.get(Case, o.case_id).animal_category,
        "description": db.get(Case, o.case_id).description, "priority": db.get(Case, o.case_id).priority,
        "status": o.status, "attempt_no": o.attempt_no, "distance_km": o.distance_km,
        "deadline_at": o.deadline_at.isoformat(), "response_reason": o.response_reason} for o in offers]

@router.post("/responder/offers/{offer_id}/accept")
def accept_offer(offer_id: str, user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    offer = db.get(AssignmentOffer, offer_id)
    if not profile or not offer or offer.responder_id != profile.id: raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "PENDING": raise HTTPException(status_code=409, detail=f"Offer is {offer.status.lower()}")
    deadline = offer.deadline_at
    if deadline.tzinfo is None: deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= utcnow():
        process_expired_offers(db); raise HTTPException(status_code=409, detail="Offer deadline expired")
    case = db.get(Case, offer.case_id)
    if case.status != "ASSIGNMENT_PENDING": raise HTTPException(status_code=409, detail="Case is no longer awaiting this offer")
    offer.status = "ACCEPTED"; offer.responded_at = utcnow(); case.status = "ASSIGNED"; case.owner_organization_id = profile.organization_id
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="ASSIGNMENT_ACCEPTED", from_status="ASSIGNMENT_PENDING", to_status="ASSIGNED",
        message=f"{user.full_name} accepted assignment offer #{offer.attempt_no}. Case ownership transferred to the responder."))
    db.commit(); return {"status": "ACCEPTED", "case_id": case.public_id, "message": "You are now the accountable responder for this case."}

@router.post("/responder/offers/{offer_id}/decline")
def decline_offer(offer_id: str, payload: OfferResponse, user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id)); offer = db.get(AssignmentOffer, offer_id)
    if not profile or not offer or offer.responder_id != profile.id: raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "PENDING": raise HTTPException(status_code=409, detail=f"Offer is {offer.status.lower()}")
    offer.status = "DECLINED"; offer.responded_at = utcnow(); offer.response_reason = (payload.reason or "No reason provided")[:500]
    case = db.get(Case, offer.case_id)
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="ASSIGNMENT_DECLINED", from_status=case.status,
        message=f"{user.full_name} declined offer #{offer.attempt_no}. Reason: {offer.response_reason}"))
    db.commit()
    next_offer = issue_next_offer(db, case, user.id)
    if next_offer:
        next_profile = db.get(ResponderProfile, next_offer.responder_id); next_user = db.get(User, next_profile.user_id)
        return {"status": "DECLINED", "next_responder": next_user.full_name, "next_offer_deadline": next_offer.deadline_at.isoformat()}
    return {"status": "NEEDS_COORDINATOR", "message": "No eligible responders remain. Coordinator action is required."}

@router.post("/jobs/process-deadlines")
def process_deadlines(_: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    return {"expired_offers_processed": process_expired_offers(db)}

@router.post("/coordinator/cases/{public_id}/handoffs", status_code=201)
def request_handoff(public_id: str, payload: dict, user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    target_id = str(payload.get("to_organization_id", "")); reason = str(payload.get("reason", "")).strip()
    target = db.get(Organization, target_id)
    if not target or not target.is_verified: raise HTTPException(status_code=400, detail="Target organization must exist and be verified")
    if len(reason) < 8: raise HTTPException(status_code=422, detail="A handoff reason of at least 8 characters is required")
    if user.role != UserRole.ADMIN and user.organization_id != case.owner_organization_id:
        raise HTTPException(status_code=403, detail="Only the current owning organization may initiate a handoff")
    if target.id == case.owner_organization_id: raise HTTPException(status_code=409, detail="Case is already owned by this organization")
    pending = db.scalar(select(CaseHandoff.id).where(CaseHandoff.case_id == case.id, CaseHandoff.status == "PENDING"))
    if pending: raise HTTPException(status_code=409, detail="A handoff is already awaiting acceptance")
    handoff = CaseHandoff(case_id=case.id, from_organization_id=case.owner_organization_id, to_organization_id=target.id,
        initiated_by=user.id, status="PENDING", reason=reason, deadline_at=utcnow()+timedelta(minutes=10))
    db.add(handoff); db.flush()
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="HANDOFF_REQUESTED", message=f"Handoff requested to {target.name}. Current ownership remains unchanged until acceptance."))
    db.commit(); db.refresh(handoff)
    return {"handoff_id": handoff.id, "status": handoff.status, "deadline_at": handoff.deadline_at.isoformat(), "current_owner_organization_id": case.owner_organization_id}

@router.post("/coordinator/handoffs/{handoff_id}/accept")
def accept_handoff(handoff_id: str, user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    handoff = db.get(CaseHandoff, handoff_id)
    if not handoff: raise HTTPException(status_code=404, detail="Handoff not found")
    if handoff.status != "PENDING": raise HTTPException(status_code=409, detail=f"Handoff is {handoff.status.lower()}")
    if user.role != UserRole.ADMIN and user.organization_id != handoff.to_organization_id:
        raise HTTPException(status_code=403, detail="Only the receiving organization's coordinator may accept")
    deadline = handoff.deadline_at
    if deadline.tzinfo is None: deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= utcnow():
        handoff.status = "EXPIRED"; handoff.responded_at = utcnow(); db.commit()
        raise HTTPException(status_code=409, detail="Handoff deadline expired; existing ownership is unchanged")
    case = db.get(Case, handoff.case_id); previous = case.owner_organization_id
    if previous != handoff.from_organization_id: raise HTTPException(status_code=409, detail="Case ownership changed; this handoff is stale")
    handoff.status = "ACCEPTED"; handoff.responded_at = utcnow(); case.owner_organization_id = handoff.to_organization_id
    target = db.get(Organization, handoff.to_organization_id)
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="HANDOFF_ACCEPTED", message=f"{target.name} accepted the handoff. Ownership transferred only after explicit acceptance."))
    db.commit(); return {"status": "ACCEPTED", "case_id": case.public_id, "owner_organization_id": case.owner_organization_id}

@router.post("/coordinator/handoffs/{handoff_id}/decline")
def decline_handoff(handoff_id: str, payload: OfferResponse, user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    handoff = db.get(CaseHandoff, handoff_id)
    if not handoff: raise HTTPException(status_code=404, detail="Handoff not found")
    if user.role != UserRole.ADMIN and user.organization_id != handoff.to_organization_id: raise HTTPException(status_code=403, detail="Only receiving organization may decline")
    if handoff.status != "PENDING": raise HTTPException(status_code=409, detail=f"Handoff is {handoff.status.lower()}")
    handoff.status = "DECLINED"; handoff.responded_at = utcnow()
    db.add(CaseEvent(case_id=handoff.case_id, actor_id=user.id, event_type="HANDOFF_DECLINED", message=f"Receiving organization declined the handoff. Reason: {(payload.reason or 'Not provided')[:500]}. Existing ownership is unchanged."))
    db.commit(); return {"status": "DECLINED", "owner_unchanged": True}

@router.patch("/responder/cases/{public_id}/status")
def update_rescue_progress(public_id: str, payload: dict, user: User = Depends(require_roles(UserRole.RESCUER)), db: Session = Depends(get_db)):
    next_status = str(payload.get("status", "")).upper()
    if next_status not in ("IN_PROGRESS", "ON_SCENE"):
        raise HTTPException(status_code=422, detail="Responders may set progress to IN_PROGRESS or ON_SCENE only")
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    accepted = profile and case and db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id,
        AssignmentOffer.responder_id == profile.id, AssignmentOffer.status == "ACCEPTED"))
    if not accepted: raise HTTPException(status_code=404, detail="Accepted case assignment not found")
    allowed = {"ASSIGNED": "IN_PROGRESS", "IN_PROGRESS": "ON_SCENE"}
    if allowed.get(case.status) != next_status:
        raise HTTPException(status_code=409, detail=f"Invalid progress transition from {case.status} to {next_status}")
    previous = case.status; case.status = next_status
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type=f"CASE_{next_status}", from_status=previous, to_status=next_status,
        message=f"Assigned responder {user.full_name} updated rescue progress to {next_status.replace('_', ' ').lower()}."))
    db.commit(); return {"case_id": case.public_id, "status": case.status}


# ============================================================
# STAGE 5: AI INCIDENT INTELLIGENCE
# ============================================================
import hashlib
from fastapi import Form
from app.services.ai_extraction import extract_incident
from app.models.entities import RescueEvidence, ResponderReliabilityScore, Notification
from app.services.reliability import update_reliability_score
from app.services.notifications import create_notification, notify_case_event

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "ResQNet API", "version": "5-8"}

@router.get("/ai/status")
def ai_status(_: User = Depends(get_current_user)):
    return {
        "gemini_configured": bool(settings.gemini_api_key),
        "whisper_configured": bool(settings.whisper_api_key),
        "features": {
            "incident_extraction": True,
            "voice_transcription": bool(settings.whisper_api_key),
            "image_classification": False,
        },
    }

@router.post("/ai/extract-incident")
def ai_extract_incident(payload: dict, user: User = Depends(get_current_user)):
    text = str(payload.get("text", "")).strip()[:2000]
    if not text:
        raise HTTPException(status_code=422, detail="Text is required")
    result = extract_incident(text)
    return result.model_dump()

@router.post("/cases/{public_id}/audio-report", status_code=201)
async def upload_audio_report(
    public_id: str,
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.CITIZEN and case.reporter_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    ALLOWED_AUDIO = {
        "audio/wav", "audio/mpeg", "audio/mp3", "audio/ogg",
        "audio/webm", "audio/mp4", "audio/m4a", "video/webm",
    }
    if audio.content_type not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    MAX_AUDIO = 10 * 1024 * 1024
    content = await audio.read(MAX_AUDIO + 1)
    if len(content) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio file must not exceed 10 MB")
    audio_dir = UPLOAD_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    suffix_map = {
        "audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
        "audio/ogg": ".ogg", "audio/webm": ".webm", "video/webm": ".webm",
        "audio/mp4": ".m4a", "audio/m4a": ".m4a",
    }
    suffix = suffix_map.get(audio.content_type or "", ".audio")
    filename = f"{case.id}-{uuid.uuid4().hex}{suffix}"
    target = audio_dir / filename
    target.write_bytes(content)
    db.add(CaseEvent(
        case_id=case.id, actor_id=user.id,
        event_type="AUDIO_REPORT_UPLOADED",
        message="Voice audio report uploaded.",
    ))
    db.commit()
    transcription = None
    if settings.whisper_api_key:
        try:
            import httpx
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.whisper_api_key}"},
                    files={"file": (filename, content, audio.content_type)},
                    data={"model": "whisper-1"},
                )
                if r.status_code == 200:
                    transcription = r.json().get("text")
        except Exception:
            pass
    return {
        "audio_saved": True, "filename": filename,
        "transcription": transcription,
        "note": "Transcription requires WHISPER_API_KEY" if not settings.whisper_api_key else None,
    }


# ============================================================
# STAGE 6: EVIDENCE AND VERIFICATION
# ============================================================
ALLOWED_EVIDENCE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm"}
MAX_EVIDENCE_IMAGE = 10 * 1024 * 1024
MAX_EVIDENCE_VIDEO = 50 * 1024 * 1024

@router.post("/cases/{public_id}/evidence", status_code=201)
async def submit_evidence(
    public_id: str,
    evidence_type: str = Form(...),
    rescue_notes: str = Form(None),
    animal_condition: str = Form(None),
    gps_lat: float = Form(None),
    gps_lon: float = Form(None),
    destination: str = Form(None),
    handover_details: str = Form(None),
    file: UploadFile = File(None),
    user: User = Depends(require_roles(UserRole.RESCUER)),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=403, detail="No responder profile")
    offer = db.scalar(select(AssignmentOffer).where(
        AssignmentOffer.case_id == case.id,
        AssignmentOffer.responder_id == profile.id,
        AssignmentOffer.status == "ACCEPTED",
    ))
    if not offer:
        raise HTTPException(status_code=403, detail="You must have an accepted assignment to submit evidence")
    file_path_str = None
    file_hash_str = None
    file_size_int = None
    mime_str = None
    if file and file.filename:
        ct = file.content_type or ""
        if evidence_type in ("before_photo", "after_photo"):
            if ct not in ALLOWED_EVIDENCE_TYPES:
                raise HTTPException(status_code=415, detail="Only JPEG, PNG, WebP images accepted for photos")
            content = await file.read(MAX_EVIDENCE_IMAGE + 1)
            if len(content) > MAX_EVIDENCE_IMAGE:
                raise HTTPException(status_code=413, detail="Image must not exceed 10 MB")
        elif evidence_type == "video":
            if ct not in ALLOWED_VIDEO_TYPES:
                raise HTTPException(status_code=415, detail="Only MP4 and WebM accepted for video")
            content = await file.read(MAX_EVIDENCE_VIDEO + 1)
            if len(content) > MAX_EVIDENCE_VIDEO:
                raise HTTPException(status_code=413, detail="Video must not exceed 50 MB")
        else:
            content = await file.read(MAX_EVIDENCE_IMAGE + 1)
        file_hash_str = hashlib.sha256(content).hexdigest()
        file_size_int = len(content)
        mime_str = ct
        evidence_dir = UPLOAD_DIR / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ext = ALLOWED_EVIDENCE_TYPES.get(ct) or ALLOWED_VIDEO_TYPES.get(ct) or ".bin"
        fname = f"{case.id}-{uuid.uuid4().hex}{ext}"
        (evidence_dir / fname).write_bytes(content)
        file_path_str = str(evidence_dir / fname)
    evidence = RescueEvidence(
        case_id=case.id, responder_id=profile.id,
        evidence_type=evidence_type, file_path=file_path_str,
        file_hash=file_hash_str, file_size=file_size_int, mime_type=mime_str,
        rescue_notes=rescue_notes, animal_condition=animal_condition,
        gps_latitude=gps_lat, gps_longitude=gps_lon,
        destination=destination, handover_details=handover_details,
    )
    db.add(evidence)
    db.add(CaseEvent(
        case_id=case.id, actor_id=user.id,
        event_type="EVIDENCE_SUBMITTED",
        message=f"Evidence of type '{evidence_type}' submitted by {user.full_name}.",
    ))
    if case.status in ("RESCUED", "VERIFICATION_PENDING") and evidence_type == "after_photo":
        case.status = "VERIFICATION_PENDING"
        db.add(CaseEvent(
            case_id=case.id, actor_id=user.id,
            event_type="VERIFICATION_REQUESTED",
            to_status="VERIFICATION_PENDING",
            message="Case evidence submitted; awaiting coordinator verification.",
        ))
    db.commit()
    db.refresh(evidence)
    return {
        "id": evidence.id, "evidence_type": evidence.evidence_type,
        "has_file": bool(file_path_str), "file_hash": file_hash_str,
        "file_size": file_size_int, "created_at": evidence.created_at.isoformat(),
    }

@router.get("/cases/{public_id}/evidence")
def get_evidence(
    public_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role not in (UserRole.COORDINATOR, UserRole.ADMIN):
        if user.role == UserRole.RESCUER:
            profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
            if not profile:
                raise HTTPException(status_code=403, detail="Forbidden")
            offer = db.scalar(select(AssignmentOffer).where(
                AssignmentOffer.case_id == case.id,
                AssignmentOffer.responder_id == profile.id,
            ))
            if not offer:
                raise HTTPException(status_code=403, detail="Forbidden")
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    evidences = db.scalars(
        select(RescueEvidence)
        .where(RescueEvidence.case_id == case.id)
        .order_by(RescueEvidence.created_at.asc())
    ).all()
    return [{
        "id": e.id, "evidence_type": e.evidence_type,
        "has_file": bool(e.file_path), "file_hash": e.file_hash,
        "file_size": e.file_size, "mime_type": e.mime_type,
        "rescue_notes": e.rescue_notes, "animal_condition": e.animal_condition,
        "destination": e.destination, "handover_details": e.handover_details,
        "created_at": e.created_at.isoformat(),
    } for e in evidences]

@router.get("/cases/{public_id}/evidence/{evidence_id}/file")
def get_evidence_file(
    public_id: str, evidence_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    evidence = db.scalar(select(RescueEvidence).where(
        RescueEvidence.id == evidence_id,
        RescueEvidence.case_id == case.id,
    ))
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if user.role not in (UserRole.COORDINATOR, UserRole.ADMIN):
        if user.role == UserRole.RESCUER:
            profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
            if not profile or evidence.responder_id != profile.id:
                raise HTTPException(status_code=403, detail="Forbidden")
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    if not evidence.file_path or not Path(evidence.file_path).is_file():
        raise HTTPException(status_code=404, detail="File not available")
    return FileResponse(evidence.file_path, media_type=evidence.mime_type or "application/octet-stream")

@router.post("/cases/{public_id}/verify")
def verify_case(
    public_id: str, payload: dict,
    user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("VERIFICATION_PENDING", "RESCUED"):
        raise HTTPException(status_code=409, detail=f"Case status is {case.status}; verification not applicable")
    decision = str(payload.get("decision", "")).upper()
    reason = str(payload.get("reason", "")).strip()
    if decision not in ("APPROVED", "REJECTED", "REQUEST_MORE"):
        raise HTTPException(status_code=422, detail="decision must be APPROVED, REJECTED, or REQUEST_MORE")
    if len(reason) < 5:
        raise HTTPException(status_code=422, detail="Reason must be at least 5 characters")
    if decision == "APPROVED":
        previous = case.status
        case.status = "VERIFIED"
        db.add(CaseEvent(
            case_id=case.id, actor_id=user.id,
            event_type="RESCUE_VERIFIED",
            from_status=previous, to_status="VERIFIED",
            message=f"Rescue verified by {user.full_name}. Reason: {reason}",
        ))
        offer = db.scalar(select(AssignmentOffer).where(
            AssignmentOffer.case_id == case.id,
            AssignmentOffer.status == "ACCEPTED",
        ))
        if offer:
            try:
                update_reliability_score(db, offer.responder_id)
            except Exception:
                pass
        try:
            create_notification(
                db, case.reporter_id, "RESCUE_VERIFIED",
                "Your rescue case has been verified!",
                f"Case {case.public_id} has been verified as successfully rescued. {reason}",
                case_id=case.id,
            )
            db.commit()
        except Exception:
            db.rollback()
    elif decision == "REJECTED":
        db.add(CaseEvent(
            case_id=case.id, actor_id=user.id,
            event_type="VERIFICATION_REJECTED",
            message=f"Verification rejected by {user.full_name}. Reason: {reason}",
        ))
    else:
        db.add(CaseEvent(
            case_id=case.id, actor_id=user.id,
            event_type="EVIDENCE_REQUESTED",
            message=f"Additional evidence requested by {user.full_name}. Reason: {reason}",
        ))
    db.commit()
    return {"decision": decision, "case_status": case.status, "message": "Verification decision recorded."}

@router.post("/cases/{public_id}/close")
def close_case(
    public_id: str, payload: dict,
    user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("VERIFIED", "CANCELLED", "REJECTED"):
        raise HTTPException(status_code=409,
            detail=f"Case must be VERIFIED, CANCELLED, or REJECTED to close. Current: {case.status}")
    reason = str(payload.get("reason", "")).strip()
    previous = case.status
    case.status = "CLOSED"
    db.add(CaseEvent(
        case_id=case.id, actor_id=user.id,
        event_type="CASE_CLOSED",
        from_status=previous, to_status="CLOSED",
        message=f"Case closed by {user.full_name}. {reason}",
    ))
    db.commit()
    return {"status": "CLOSED", "message": "Case has been closed."}

# Extended progress state machine
VALID_PROGRESS_TRANSITIONS = {
    "ASSIGNED": ["EN_ROUTE", "IN_PROGRESS"],
    "EN_ROUTE": ["ARRIVED", "ON_SCENE"],
    "ARRIVED": ["RESCUE_IN_PROGRESS", "IN_PROGRESS"],
    "RESCUE_IN_PROGRESS": ["RESCUED"],
    "IN_PROGRESS": ["ON_SCENE", "RESCUED", "RESCUE_IN_PROGRESS"],
    "ON_SCENE": ["RESCUED", "RESCUE_IN_PROGRESS"],
    "RESCUED": ["VERIFICATION_PENDING"],
}

@router.patch("/cases/{public_id}/progress")
def update_case_progress(
    public_id: str, payload: dict,
    user: User = Depends(require_roles(UserRole.RESCUER)),
    db: Session = Depends(get_db),
):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=403, detail="No responder profile")
    offer = db.scalar(select(AssignmentOffer).where(
        AssignmentOffer.case_id == case.id,
        AssignmentOffer.responder_id == profile.id,
        AssignmentOffer.status == "ACCEPTED",
    ))
    if not offer:
        raise HTTPException(status_code=403, detail="You must have an accepted assignment")
    new_status = str(payload.get("status", "")).upper()
    allowed = VALID_PROGRESS_TRANSITIONS.get(case.status, [])
    if new_status not in allowed:
        raise HTTPException(status_code=409,
            detail=f"Cannot transition from {case.status} to {new_status}. Allowed: {allowed}")
    previous = case.status
    case.status = new_status
    if new_status == "RESCUED":
        case.status = "VERIFICATION_PENDING"
        new_status = "VERIFICATION_PENDING"
    db.add(CaseEvent(
        case_id=case.id, actor_id=user.id,
        event_type=f"STATUS_{new_status}",
        from_status=previous, to_status=new_status,
        message=f"Case progress updated to {new_status.replace('_', ' ').title()} by {user.full_name}.",
    ))
    db.commit()
    return {"status": case.status, "message": f"Progress updated to {case.status}"}


# ============================================================
# NOTIFICATIONS
# ============================================================
@router.get("/notifications")
def get_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = False,
):
    q = (select(Notification)
         .where(Notification.user_id == user.id)
         .order_by(Notification.created_at.desc())
         .limit(50))
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    notifs = db.scalars(q).all()
    return [{
        "id": n.id, "event_type": n.event_type, "title": n.title,
        "body": n.body, "is_read": n.is_read, "case_id": n.case_id,
        "created_at": n.created_at.isoformat(),
    } for n in notifs]

@router.get("/notifications/count")
def notification_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    )) or 0
    return {"unread": count}

@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.scalar(select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == user.id,
    ))
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"status": "read"}


# ============================================================
# ANALYTICS (STAGE 7)
# ============================================================
@router.get("/analytics/summary")
def analytics_summary(
    user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(Case.id))) or 0
    by_priority = {}
    for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NEEDS_REVIEW"):
        by_priority[p] = db.scalar(select(func.count(Case.id)).where(Case.priority == p)) or 0
    by_status = {}
    for s in ("REPORTED", "TRIAGED", "ASSIGNMENT_PENDING", "ASSIGNED", "IN_PROGRESS",
              "ON_SCENE", "EN_ROUTE", "ARRIVED", "RESCUE_IN_PROGRESS", "RESCUED",
              "VERIFICATION_PENDING", "VERIFIED", "CLOSED", "ESCALATED", "NEEDS_COORDINATOR"):
        cnt = db.scalar(select(func.count(Case.id)).where(Case.status == s)) or 0
        if cnt > 0:
            by_status[s] = cnt
    by_category = {}
    rows = db.execute(select(Case.animal_category, func.count(Case.id)).group_by(Case.animal_category)).all()
    for cat, cnt in rows:
        by_category[cat] = cnt
    verified = by_status.get("VERIFIED", 0) + by_status.get("CLOSED", 0)
    completion_rate = round(verified / total * 100, 1) if total > 0 else 0
    return {
        "total_cases": total, "by_priority": by_priority, "by_status": by_status,
        "by_category": by_category, "verified_rescues": verified,
        "completion_rate_pct": completion_rate, "data_label": "Live database records",
    }

@router.get("/responder/my-reliability")
def my_reliability(
    user: User = Depends(require_roles(UserRole.RESCUER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="No responder profile found")
    record = db.scalar(select(ResponderReliabilityScore).where(
        ResponderReliabilityScore.responder_id == profile.id,
    ))
    if not record:
        return {"score": 100.0, "explanation": "No assignment history yet.", "total_assignments": 0}
    return {
        "score": record.reliability_score,
        "explanation": record.score_explanation,
        "total_assignments": record.total_assignments,
        "accepted": record.accepted_count,
        "declined": record.declined_count,
        "expired": record.expired_count,
        "verified": record.verified_count,
    }
