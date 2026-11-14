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

@router.post("/admin/users", status_code=201)
def admin_create_user(payload: dict, _: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    full_name = str(payload.get("full_name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    try:
        role = UserRole(str(payload.get("role", "")))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid account role")
    if role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin accounts cannot be created through this endpoint")
    if len(full_name) < 2 or len(email) < 5 or len(password) < 10:
        raise HTTPException(status_code=422, detail="Name, valid email and password of at least 10 characters are required")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    organization_id = payload.get("organization_id")
    if role == UserRole.COORDINATOR:
        organization = db.get(Organization, organization_id) if organization_id else None
        if not organization or not organization.is_verified:
            raise HTTPException(status_code=422, detail="A coordinator must be assigned to an existing verified organization")
    user = User(full_name=full_name[:120], email=email, password_hash=hash_password(password), role=role,
                organization_id=organization_id if role == UserRole.COORDINATOR else None, is_active=True, is_verified=False)
    db.add(user); db.flush()
    if role == UserRole.RESCUER:
        profile = ResponderProfile(user_id=user.id)
        db.add(profile); db.flush()
        db.add(Availability(responder_id=profile.id, is_available=False))
    db.commit(); db.refresh(user)
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role.value,
            "is_active": user.is_active, "is_verified": user.is_verified}

@router.patch("/admin/users/{user_id}/status")
def set_user_status(user_id: str, payload: dict, admin: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and payload.get("is_active") is False:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own administrator account")
    if target.role == UserRole.ADMIN and target.is_active and payload.get("is_active") is False:
        active_admins = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    if not isinstance(payload.get("is_active"), bool):
        raise HTTPException(status_code=422, detail="is_active must be a boolean")
    target.is_active = payload["is_active"]
    db.commit()
    return {"id": target.id, "is_active": target.is_active}

@router.patch("/admin/users/{user_id}/verification")
def set_user_verification(user_id: str, payload: dict, _: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role != UserRole.RESCUER:
        raise HTTPException(status_code=422, detail="Only responder accounts use responder verification")
    if not isinstance(payload.get("verified"), bool):
        raise HTTPException(status_code=422, detail="verified must be a boolean")
    target.is_verified = payload["verified"]
    profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == target.id))
    if profile:
        profile.verified_at = utcnow() if target.is_verified else None
    db.commit()
    return {"id": target.id, "is_verified": target.is_verified}

@router.post("/admin/organizations", status_code=201)
def create_organization(payload: dict, _: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    name = str(payload.get("name", "")).strip()
    if len(name) < 3:
        raise HTTPException(status_code=422, detail="Organization name must contain at least 3 characters")
    organization = Organization(name=name[:180], organization_type=str(payload.get("type", "ngo"))[:40],
        city=str(payload.get("city", "Salem"))[:100], state=str(payload.get("state", "Tamil Nadu"))[:100], is_verified=False)
    db.add(organization); db.commit(); db.refresh(organization)
    return {"id": organization.id, "name": organization.name, "type": organization.organization_type,
        "city": organization.city, "state": organization.state, "verified": organization.is_verified}

@router.patch("/admin/organizations/{organization_id}/verification")
def verify_organization(organization_id: str, payload: dict, _: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not isinstance(payload.get("verified"), bool):
        raise HTTPException(status_code=422, detail="verified must be a boolean")
    organization.is_verified = payload["verified"]
    db.commit()
    return {"id": organization.id, "verified": organization.is_verified}

# Stage 3: citizen reporting, coordinator triage, case tracking and event history.
import json, math, os, re, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import File, UploadFile
from fastapi.responses import FileResponse
from app.models.entities import CaseEvent
from app.schemas.cases import CaseCreate, CaseRead, TriageUpdate, CaseEventRead
from app.services.triage import suggest_priority

UPLOAD_DIR = Path(settings.upload_dir).resolve()
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
    elif user.role == UserRole.COORDINATOR:
        if not user.organization_id:
            return []
        query = query.where((Case.owner_organization_id == user.organization_id) | (Case.owner_organization_id.is_(None)))
    elif user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not permitted to view cases")
    cases = db.scalars(query).all()
    return [_case_read(db, c, include_events=False) for c in cases]

@router.get("/cases/{public_id}", response_model=CaseRead)
def get_case(public_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.CITIZEN and case.reporter_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
        raise HTTPException(status_code=404, detail="Case not found")
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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
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
def get_eligible_responders(public_id: str, coordinator: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if coordinator.role == UserRole.COORDINATOR and coordinator.organization_id and case.owner_organization_id not in (None, coordinator.organization_id):
        raise HTTPException(status_code=404, detail="Case not found")
    return [{"responder_id": x["user"].id, "name": x["user"].full_name, "organization_id": x["profile"].organization_id,
        "distance_km": x["distance_km"], "score": x["score"], "service_radius_km": x["profile"].service_radius_km,
        "capacity": x["profile"].capacity} for x in eligible_responders(db, case)]

@router.post("/coordinator/cases/{public_id}/assign", status_code=201)
def assign_case(public_id: str, coordinator: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    if coordinator.role == UserRole.COORDINATOR and coordinator.organization_id and case.owner_organization_id not in (None, coordinator.organization_id):
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("TRIAGED", "NEEDS_COORDINATOR"):
        raise HTTPException(status_code=409, detail=f"Case must be TRIAGED before assignment (current: {case.status})")
    if db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id, AssignmentOffer.status == "PENDING")):
        raise HTTPException(status_code=409, detail="A pending assignment offer already exists")
    if coordinator.role == UserRole.COORDINATOR and coordinator.organization_id:
        case.owner_organization_id = coordinator.organization_id
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
    offer.status = "ACCEPTED"; offer.responded_at = utcnow(); case.status = "ASSIGNED"; case.owner_organization_id = profile.organization_id or case.owner_organization_id
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="ASSIGNMENT_ACCEPTED", from_status="ASSIGNMENT_PENDING", to_status="ASSIGNED",
        message=f"{user.full_name} accepted assignment offer #{offer.attempt_no}. Case ownership transferred to the responder."))
    db.commit()
    from app.services.notifications import notify_case_event
    notify_case_event(db, case.id, "ASSIGNMENT_ACCEPTED", "Responder accepted the case", f"A responder accepted case {case.public_id}.", exclude_user_id=user.id)
    return {"status": "ACCEPTED", "case_id": case.public_id, "message": "You are now the accountable responder for this case."}

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
    from app.services.notifications import notify_case_event
    notify_case_event(db, case.id, "ASSIGNMENT_DECLINED", "Responder declined the offer", f"A responder declined case {case.public_id}; the next eligible responder is being checked.", exclude_user_id=user.id)
    next_offer = issue_next_offer(db, case, user.id)
    if next_offer:
        next_profile = db.get(ResponderProfile, next_offer.responder_id); next_user = db.get(User, next_profile.user_id)
        return {"status": "DECLINED", "next_responder": next_user.full_name, "next_offer_deadline": next_offer.deadline_at.isoformat()}
    return {"status": "NEEDS_COORDINATOR", "message": "No eligible responders remain. Coordinator action is required."}

@router.post("/jobs/process-deadlines")
def process_deadlines(_: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)):
    return {"expired_offers_processed": process_expired_offers(db)}

@router.get("/coordinator/handoffs")
def list_handoffs(user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    query = select(CaseHandoff).order_by(CaseHandoff.created_at.desc()).limit(200)
    if user.role == UserRole.COORDINATOR:
        if not user.organization_id:
            return []
        query = query.where((CaseHandoff.from_organization_id == user.organization_id) | (CaseHandoff.to_organization_id == user.organization_id))
    rows = db.scalars(query).all()
    result = []
    for h in rows:
        case = db.get(Case, h.case_id)
        source = db.get(Organization, h.from_organization_id) if h.from_organization_id else None
        target = db.get(Organization, h.to_organization_id)
        result.append({"id": h.id, "case_public_id": case.public_id if case else None,
            "case_description": case.description[:180] if case else "",
            "from_organization_id": h.from_organization_id, "from_organization": source.name if source else "Unassigned",
            "to_organization_id": h.to_organization_id, "to_organization": target.name if target else "Unknown",
            "status": h.status, "reason": h.reason, "deadline_at": h.deadline_at.isoformat(),
            "created_at": h.created_at.isoformat(), "incoming": user.role == UserRole.ADMIN or h.to_organization_id == user.organization_id})
    return result

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
    from app.services.notifications import create_notification
    for recipient in db.scalars(select(User).where(User.role == UserRole.COORDINATOR, User.organization_id == target.id, User.is_active.is_(True))).all():
        create_notification(db, recipient.id, "HANDOFF_REQUESTED", "Incoming case handoff", f"{case.public_id}: {reason}", case.id)
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
    from app.services.notifications import create_notification
    source_org = handoff.from_organization_id
    if source_org:
        for recipient in db.scalars(select(User).where(User.role == UserRole.COORDINATOR, User.organization_id == source_org, User.is_active.is_(True))).all():
            create_notification(db, recipient.id, "HANDOFF_ACCEPTED", "Case handoff accepted", f"{case.public_id} is now owned by {target.name}.", case.id)
    db.commit(); return {"status": "ACCEPTED", "case_id": case.public_id, "owner_organization_id": case.owner_organization_id}

@router.post("/coordinator/handoffs/{handoff_id}/decline")
def decline_handoff(handoff_id: str, payload: OfferResponse, user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)), db: Session = Depends(get_db)):
    handoff = db.get(CaseHandoff, handoff_id)
    if not handoff: raise HTTPException(status_code=404, detail="Handoff not found")
    if user.role != UserRole.ADMIN and user.organization_id != handoff.to_organization_id: raise HTTPException(status_code=403, detail="Only receiving organization may decline")
    if handoff.status != "PENDING": raise HTTPException(status_code=409, detail=f"Handoff is {handoff.status.lower()}")
    handoff.status = "DECLINED"; handoff.responded_at = utcnow()
    db.add(CaseEvent(case_id=handoff.case_id, actor_id=user.id, event_type="HANDOFF_DECLINED", message=f"Receiving organization declined the handoff. Reason: {(payload.reason or 'Not provided')[:500]}. Existing ownership is unchanged."))
    from app.services.notifications import create_notification
    if handoff.from_organization_id:
        for recipient in db.scalars(select(User).where(User.role == UserRole.COORDINATOR, User.organization_id == handoff.from_organization_id, User.is_active.is_(True))).all():
            create_notification(db, recipient.id, "HANDOFF_DECLINED", "Case handoff declined", f"Handoff for case {handoff.case_id} was declined.", handoff.case_id)
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
            "image_classification": bool(settings.gemini_api_key),
        },
    }

@router.post("/ai/extract-incident")
def ai_extract_incident(payload: dict, user: User = Depends(get_current_user)):
    text = str(payload.get("text", "")).strip()[:2000]
    if not text:
        raise HTTPException(status_code=422, detail="Text is required")
    result = extract_incident(text)
    return result.model_dump()

@router.post("/ai/classify-image")
async def classify_animal_image(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Optional Gemini vision classification. Never fabricates a result when unconfigured."""
    allowed = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}
    mime = file.content_type or ""
    if mime not in allowed:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG or WebP image")
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be between 1 byte and 5 MB")
    if not content.startswith(allowed[mime]) or (mime == "image/webp" and content[8:12] != b"WEBP"):
        raise HTTPException(status_code=415, detail="Image signature does not match its MIME type")
    if not settings.gemini_api_key:
        return {"available": False, "classification": None, "confidence": None,
                "message": "Image classification is unavailable: configure GEMINI_API_KEY. Please select the animal category manually."}
    import base64, httpx
    prompt = "Identify the visible animal species/category in this image. Return JSON only with keys animal_category, confidence (0 to 1), visible_evidence, uncertainty. Do not infer injuries or medical conditions. If no animal is clearly visible, return animal_category as Unknown and low confidence."
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode("ascii")}}]}],
               "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
        response.raise_for_status()
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw)
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
        return {"available": True, "classification": str(parsed.get("animal_category", "Unknown"))[:80],
                "confidence": confidence, "visible_evidence": str(parsed.get("visible_evidence", ""))[:500],
                "uncertainty": str(parsed.get("uncertainty", ""))[:500], "requires_user_confirmation": True}
    except Exception:
        return {"available": False, "classification": None, "confidence": None,
                "message": "Image classification provider failed. Continue with manual animal selection."}

@router.patch("/cases/{public_id}/voice-transcript")
def save_voice_transcript(public_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case or case.reporter_id != user.id or user.role != UserRole.CITIZEN:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status not in ("REPORTED", "TRIAGED"):
        raise HTTPException(status_code=409, detail="The case description can no longer be edited after assignment")
    transcript = str(payload.get("transcript", "")).strip()
    if len(transcript) < 5:
        raise HTTPException(status_code=422, detail="Transcript must contain at least 5 characters")
    marker_text = "\n\nVoice transcript (reporter-confirmed): "
    if "Voice transcript (reporter-confirmed):" not in case.description:
        case.description = (case.description + marker_text + transcript)[:5000]
    else:
        case.description = case.description.split(marker_text)[0] + marker_text + transcript
        case.description = case.description[:5000]
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="VOICE_TRANSCRIPT_CONFIRMED", message="Reporter confirmed and added the voice transcript to the case description."))
    db.commit()
    return {"status": "saved", "description": case.description}

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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        if not profile or not db.scalar(select(AssignmentOffer.id).where(AssignmentOffer.case_id == case.id, AssignmentOffer.responder_id == profile.id, AssignmentOffer.status.in_(["PENDING", "ACCEPTED"]))):
            raise HTTPException(status_code=403, detail="Not authorized for this case")
    if user.role not in (UserRole.CITIZEN, UserRole.RESCUER, UserRole.COORDINATOR, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Not authorized")
    ALLOWED_AUDIO = {
        "audio/wav", "audio/mpeg", "audio/mp3", "audio/ogg",
        "audio/webm", "audio/mp4", "audio/m4a", "video/webm",
    }
    if audio.content_type not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    MAX_AUDIO = 10 * 1024 * 1024
    content = await audio.read(MAX_AUDIO + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    if len(content) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio file must not exceed 10 MB")
    signatures = {"audio/wav": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WAVE",
                  "audio/webm": lambda b: b.startswith(b"\x1a\x45\xdf\xa3"),
                  "video/webm": lambda b: b.startswith(b"\x1a\x45\xdf\xa3"),
                  "audio/ogg": lambda b: b.startswith(b"OggS"),
                  "audio/mpeg": lambda b: b.startswith(b"ID3") or (len(b) > 1 and b[0] == 0xff and (b[1] & 0xe0) == 0xe0)}
    if audio.content_type in signatures and not signatures[audio.content_type](content):
        raise HTTPException(status_code=415, detail="Audio signature does not match its declared type")
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


def _has_valid_file_signature(content: bytes, content_type: str) -> bool:
    """Check file magic bytes instead of trusting the client-supplied MIME type."""
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type == "video/mp4":
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if content_type == "video/webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    return False

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
    if gps_lat is not None and not -90 <= gps_lat <= 90:
        raise HTTPException(status_code=422, detail="GPS latitude must be between -90 and 90")
    if gps_lon is not None and not -180 <= gps_lon <= 180:
        raise HTTPException(status_code=422, detail="GPS longitude must be between -180 and 180")
    if evidence_type not in {"before_photo", "after_photo", "video", "note"}:
        raise HTTPException(status_code=422, detail="Unsupported evidence type")
    if evidence_type == "note" and not any((rescue_notes, animal_condition, destination, handover_details)):
        raise HTTPException(status_code=422, detail="A note must include at least one detail")
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
            raise HTTPException(status_code=415, detail="Files are only accepted for photo and video evidence")
        if not content:
            raise HTTPException(status_code=422, detail="Uploaded file is empty")
        if evidence_type in ("before_photo", "after_photo", "video") and not _has_valid_file_signature(content, ct):
            raise HTTPException(status_code=415, detail="File content does not match its declared media type")
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
    allowed = user.role in (UserRole.ADMIN, UserRole.COORDINATOR)
    if user.role == UserRole.COORDINATOR and user.organization_id:
        allowed = case.owner_organization_id in (None, user.organization_id)
    elif user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        allowed = bool(profile and db.scalar(select(AssignmentOffer.id).where(
            AssignmentOffer.case_id == case.id, AssignmentOffer.responder_id == profile.id,
            AssignmentOffer.status.in_(["PENDING", "ACCEPTED"]))))
    if not allowed:
        raise HTTPException(status_code=403, detail="Not permitted to view evidence")
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
    allowed = user.role in (UserRole.ADMIN, UserRole.COORDINATOR)
    if user.role == UserRole.COORDINATOR and user.organization_id:
        allowed = case.owner_organization_id in (None, user.organization_id)
    elif user.role == UserRole.RESCUER:
        profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
        allowed = bool(profile and evidence.responder_id == profile.id)
    if not allowed:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if not evidence.file_path or not Path(evidence.file_path).is_file():
        raise HTTPException(status_code=404, detail="File not available")
    if evidence.file_hash:
        current_hash = hashlib.sha256(Path(evidence.file_path).read_bytes()).hexdigest()
        if current_hash != evidence.file_hash:
            raise HTTPException(status_code=500, detail="Evidence integrity check failed; file is quarantined from download")
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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
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
    notify_case_event(db, case.id, f"VERIFICATION_{decision}", "Rescue verification update", f"Case {case.public_id}: {decision.replace('_', ' ').lower()}. {reason}", exclude_user_id=user.id)
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
    if user.role == UserRole.COORDINATOR and user.organization_id and case.owner_organization_id not in (None, user.organization_id):
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
    notify_case_event(db, case.id, "CASE_CLOSED", "Rescue case closed", f"Case {case.public_id} has been closed. {reason}", exclude_user_id=user.id)
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
