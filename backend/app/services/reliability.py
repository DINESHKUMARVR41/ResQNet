"""Responder reliability scoring service."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.entities import AssignmentOffer, ResponderReliabilityScore, Case, new_id


def update_reliability_score(db: Session, responder_id: str) -> dict:
    offers = db.scalars(select(AssignmentOffer).where(AssignmentOffer.responder_id == responder_id)).all()
    total = len(offers)
    accepted = sum(1 for o in offers if o.status == "ACCEPTED")
    declined = sum(1 for o in offers if o.status == "DECLINED")
    expired = sum(1 for o in offers if o.status == "EXPIRED")

    # Count verified rescues via Case status
    verified = db.scalar(select(func.count(Case.id)).where(
        Case.status == "VERIFIED",
        Case.id.in_(select(AssignmentOffer.case_id).where(
            AssignmentOffer.responder_id == responder_id,
            AssignmentOffer.status == "ACCEPTED"
        ))
    )) or 0

    score = 100.0
    score -= declined * 5
    score -= expired * 10
    score += verified * 5
    score = max(0.0, min(100.0, score))

    explanation = (
        f"Base 100. Declined offers: -{declined * 5}. "
        f"Expired offers: -{expired * 10}. Verified rescues: +{verified * 5}. "
        f"Final score: {score:.0f}/100."
    )

    record = db.scalar(select(ResponderReliabilityScore).where(
        ResponderReliabilityScore.responder_id == responder_id
    ))
    if not record:
        record = ResponderReliabilityScore(id=new_id(), responder_id=responder_id)
        db.add(record)
    record.total_assignments = total
    record.accepted_count = accepted
    record.declined_count = declined
    record.expired_count = expired
    record.verified_count = verified
    record.reliability_score = score
    record.score_explanation = explanation
    db.commit()
    db.refresh(record)
    return {"score": score, "explanation": explanation, "total": total}
