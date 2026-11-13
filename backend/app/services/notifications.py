"""Notification creation helpers."""
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.entities import Notification, User, UserRole, Case, AssignmentOffer, ResponderProfile, new_id


def create_notification(
    db: Session,
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    case_id: str | None = None,
) -> Notification:
    n = Notification(
        id=new_id(),
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        case_id=case_id,
    )
    db.add(n)
    return n


def notify_case_event(
    db: Session,
    case_id: str,
    event_type: str,
    title: str,
    body: str,
    exclude_user_id: str | None = None,
) -> None:
    case = db.get(Case, case_id)
    if not case:
        return
    recipients: set[str] = set()
    recipients.add(case.reporter_id)
    # Find accepted responder
    offer = db.scalar(
        select(AssignmentOffer).where(
            AssignmentOffer.case_id == case_id,
            AssignmentOffer.status == "ACCEPTED",
        )
    )
    if offer:
        profile = db.get(ResponderProfile, offer.responder_id)
        if profile:
            recipients.add(profile.user_id)
    # Notify coordinators
    coordinators = db.scalars(
        select(User).where(User.role == UserRole.COORDINATOR, User.is_active.is_(True))
    ).all()
    for c in coordinators:
        recipients.add(c.id)
    if exclude_user_id:
        recipients.discard(exclude_user_id)
    for uid in recipients:
        create_notification(db, uid, event_type, title, body, case_id=case_id)
    db.commit()
