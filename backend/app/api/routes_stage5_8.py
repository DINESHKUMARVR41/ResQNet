

# ============================================================
# STAGE 5: AI INCIDENT INTELLIGENCE
# ============================================================
from app.services.ai_extraction import extract_incident

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
    return result.dict()

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
    try:
        case.voice_report_path = str(target)
        db.commit()
    except Exception:
        db.rollback()
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="AUDIO_REPORT_UPLOADED",
        message="Voice audio report uploaded."))
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
        "audio_saved": True,
        "filename": filename,
        "transcription": transcription,
        "note": "Transcription requires WHISPER_API_KEY" if not settings.whisper_api_key else None,
    }

# ============================================================
# STAGE 6: EVIDENCE AND VERIFICATION
# ============================================================
import hashlib
from fastapi import Form
from app.models.entities import RescueEvidence, ResponderReliabilityScore, Notification
from app.services.reliability import update_reliability_score
from app.services.notifications import create_notification, notify_case_event

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
        filename = f"{case.id}-{uuid.uuid4().hex}{ext}"
        (evidence_dir / filename).write_bytes(content)
        file_path_str = str(evidence_dir / filename)

    evidence = RescueEvidence(
        case_id=case.id, responder_id=profile.id,
        evidence_type=evidence_type, file_path=file_path_str,
        file_hash=file_hash_str, file_size=file_size_int, mime_type=mime_str,
        rescue_notes=rescue_notes, animal_condition=animal_condition,
        gps_latitude=gps_lat, gps_longitude=gps_lon,
        destination=destination, handover_details=handover_details,
    )
    db.add(evidence)
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="EVIDENCE_SUBMITTED",
        message=f"Evidence of type '{evidence_type}' submitted by {user.full_name}."))
    if case.status == "RESCUED" and evidence_type == "after_photo":
        case.status = "VERIFICATION_PENDING"
        db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="VERIFICATION_REQUESTED",
            to_status="VERIFICATION_PENDING",
            message="Case evidence submitted; awaiting coordinator verification."))
    db.commit()
    db.refresh(evidence)
    return {
        "id": evidence.id,
        "evidence_type": evidence.evidence_type,
        "has_file": bool(file_path_str),
        "file_hash": file_hash_str,
        "file_size": file_size_int,
        "created_at": evidence.created_at.isoformat(),
    }

@router.get("/cases/{public_id}/evidence")
def get_evidence(public_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.public_id == public_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role not in (UserRole.COORDINATOR, UserRole.ADMIN):
        if user.role == UserRole.RESCUER:
            profile = db.scalar(select(ResponderProfile).where(ResponderProfile.user_id == user.id))
            if not profile:
                raise HTTPException(status_code=403, detail="Forbidden")
            offer = db.scalar(select(AssignmentOffer).where(
                AssignmentOffer.case_id == case.id, AssignmentOffer.responder_id == profile.id))
            if not offer:
                raise HTTPException(status_code=403, detail="Forbidden")
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    evidences = db.scalars(
        select(RescueEvidence).where(RescueEvidence.case_id == case.id).order_by(RescueEvidence.created_at.asc())
    ).all()
    return [{
        "id": e.id, "evidence_type": e.evidence_type, "has_file": bool(e.file_path),
        "file_hash": e.file_hash, "file_size": e.file_size, "mime_type": e.mime_type,
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
        RescueEvidence.id == evidence_id, RescueEvidence.case_id == case.id))
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
        try:
            from app.models.entities import utcnow as _utcnow
            case.verified_at = _utcnow()
            case.verified_by = user.id
            case.verification_reason = reason
        except Exception:
            pass
        db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="RESCUE_VERIFIED",
            from_status=previous, to_status="VERIFIED",
            message=f"Rescue verified by {user.full_name}. Reason: {reason}"))
        offer = db.scalar(select(AssignmentOffer).where(
            AssignmentOffer.case_id == case.id, AssignmentOffer.status == "ACCEPTED"))
        if offer:
            try:
                update_reliability_score(db, offer.responder_id)
            except Exception:
                pass
        try:
            create_notification(db, case.reporter_id, "RESCUE_VERIFIED",
                "Your rescue case has been verified!",
                f"Case {case.public_id} has been verified as successfully rescued. {reason}",
                case_id=case.id)
            db.commit()
        except Exception:
            pass
    elif decision == "REJECTED":
        try:
            case.verification_reason = f"REJECTED: {reason}"
        except Exception:
            pass
        db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="VERIFICATION_REJECTED",
            message=f"Verification rejected by {user.full_name}. Reason: {reason}"))
    else:  # REQUEST_MORE
        db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="EVIDENCE_REQUESTED",
            message=f"Additional evidence requested by {user.full_name}. Reason: {reason}"))
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
    try:
        from app.models.entities import utcnow as _utcnow
        case.closed_at = _utcnow()
    except Exception:
        pass
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type="CASE_CLOSED",
        from_status=previous, to_status="CLOSED",
        message=f"Case closed by {user.full_name}. {reason}"))
    db.commit()
    return {"status": "CLOSED", "message": "Case has been closed."}

# RESCUER PROGRESS UPDATES (extended state machine)
VALID_PROGRESS_TRANSITIONS = {
    "ASSIGNED": ["EN_ROUTE", "IN_PROGRESS"],
    "ASSIGNMENT_PENDING": [],
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
    db.add(CaseEvent(case_id=case.id, actor_id=user.id, event_type=f"STATUS_{new_status}",
        from_status=previous, to_status=new_status,
        message=f"Case progress updated to {new_status.replace('_', ' ').title()} by {user.full_name}."))
    db.commit()
    return {"status": case.status, "message": f"Progress updated to {case.status}"}

# ============================================================
# NOTIFICATIONS ENDPOINTS
# ============================================================
@router.get("/notifications")
def get_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = False,
):
    q = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    notifs = db.scalars(q).all()
    return [{
        "id": n.id, "event_type": n.event_type, "title": n.title, "body": n.body,
        "is_read": n.is_read, "case_id": n.case_id, "created_at": n.created_at.isoformat(),
    } for n in notifs]

@router.get("/notifications/count")
def notification_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False))) or 0
    return {"unread": count}

@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id))
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"status": "read"}

# ============================================================
# ANALYTICS ENDPOINTS (Stage 7)
# ============================================================
@router.get("/analytics/summary")
def analytics_summary(
    user: User = Depends(require_roles(UserRole.COORDINATOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(Case.id))) or 0
    by_priority = {}
    for priority in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NEEDS_REVIEW"):
        by_priority[priority] = db.scalar(select(func.count(Case.id)).where(Case.priority == priority)) or 0
    by_status = {}
    for status in (
        "REPORTED", "TRIAGED", "ASSIGNMENT_PENDING", "ASSIGNED", "IN_PROGRESS",
        "ON_SCENE", "EN_ROUTE", "ARRIVED", "RESCUE_IN_PROGRESS", "RESCUED",
        "VERIFICATION_PENDING", "VERIFIED", "CLOSED", "ESCALATED", "NEEDS_COORDINATOR",
    ):
        cnt = db.scalar(select(func.count(Case.id)).where(Case.status == status)) or 0
        if cnt > 0:
            by_status[status] = cnt
    by_category = {}
    rows = db.execute(select(Case.animal_category, func.count(Case.id)).group_by(Case.animal_category)).all()
    for cat, cnt in rows:
        by_category[cat] = cnt
    verified = by_status.get("VERIFIED", 0) + by_status.get("CLOSED", 0)
    completion_rate = round(verified / total * 100, 1) if total > 0 else 0
    return {
        "total_cases": total,
        "by_priority": by_priority,
        "by_status": by_status,
        "by_category": by_category,
        "verified_rescues": verified,
        "completion_rate_pct": completion_rate,
        "data_label": "Live database records",
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
        ResponderReliabilityScore.responder_id == profile.id))
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
