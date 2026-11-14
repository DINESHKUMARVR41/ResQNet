"""Transparent responder reliability scoring; an operational indicator, not a quality guarantee."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.entities import AssignmentOffer, ResponderReliabilityScore, Case, new_id


def update_reliability_score(db: Session, responder_id: str) -> dict:
    offers = db.scalars(select(AssignmentOffer).where(AssignmentOffer.responder_id == responder_id)).all()
    total = len(offers)
    accepted = sum(1 for offer in offers if offer.status == "ACCEPTED")
    declined = sum(1 for offer in offers if offer.status == "DECLINED")
    expired = sum(1 for offer in offers if offer.status == "EXPIRED")
    accepted_case_ids = [offer.case_id for offer in offers if offer.status == "ACCEPTED"]
    verified = db.scalar(select(func.count(Case.id)).where(Case.id.in_(accepted_case_ids), Case.status.in_(["VERIFIED", "CLOSED"]))) if accepted_case_ids else 0
    completed = db.scalar(select(func.count(Case.id)).where(Case.id.in_(accepted_case_ids), Case.status.in_(["RESCUED", "VERIFICATION_PENDING", "VERIFIED", "CLOSED"]))) if accepted_case_ids else 0
    # Declines are not penalized: responders may be unavailable for legitimate reasons.
    # Expiry is a weak signal only; verified completion and accepted work are rewarded.
    acceptance_component = (accepted / total * 100) if total else 100.0
    completion_component = (completed / accepted * 100) if accepted else 50.0
    verification_component = (verified / accepted * 100) if accepted else 50.0
    expiry_component = max(0.0, 100.0 - (expired / total * 100 * 0.25)) if total else 100.0
    score = round(0.30 * acceptance_component + 0.30 * completion_component + 0.30 * verification_component + 0.10 * expiry_component, 1)
    explanation = (f"Weighted operational indicator: acceptance 30% ({acceptance_component:.1f}), "
                   f"completion 30% ({completion_component:.1f}), verification 30% ({verification_component:.1f}), "
                   f"expiry reliability 10% ({expiry_component:.1f}). Declines are not penalized. "
                   f"Based on {total} offers; {completed} completed and {verified} verified.")
    record = db.scalar(select(ResponderReliabilityScore).where(ResponderReliabilityScore.responder_id == responder_id))
    if not record:
        record = ResponderReliabilityScore(id=new_id(), responder_id=responder_id)
        db.add(record)
    record.total_assignments = total
    record.accepted_count = accepted
    record.declined_count = declined
    record.expired_count = expired
    record.completed_count = completed
    record.verified_count = verified
    record.reliability_score = score
    record.score_explanation = explanation
    db.commit(); db.refresh(record)
    return {"score": score, "explanation": explanation, "total": total}
