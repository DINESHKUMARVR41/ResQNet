import enum, uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Float, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

def new_id() -> str: return str(uuid.uuid4())
def utcnow() -> datetime: return datetime.now(timezone.utc)

class UserRole(str, enum.Enum):
    CITIZEN = "citizen"
    RESCUER = "rescuer"
    COORDINATOR = "coordinator"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CITIZEN, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    responder_profile: Mapped["ResponderProfile | None"] = relationship(back_populates="user", uselist=False)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(40), default="ngo", nullable=False)
    city: Mapped[str] = mapped_column(String(100), default="Salem", nullable=False)
    state: Mapped[str] = mapped_column(String(100), default="Tamil Nadu", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class ResponderProfile(Base):
    __tablename__ = "responder_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    service_radius_km: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="responder_profile")
    skills: Mapped[list["ResponderSkill"]] = relationship(back_populates="responder", cascade="all, delete-orphan")
    availability: Mapped["Availability | None"] = relationship(back_populates="responder", uselist=False, cascade="all, delete-orphan")

class ResponderSkill(Base):
    __tablename__ = "responder_skills"
    __table_args__ = (UniqueConstraint("responder_id", "species", name="uq_responder_species"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    responder_id: Mapped[str] = mapped_column(ForeignKey("responder_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    species: Mapped[str] = mapped_column(String(60), nullable=False)
    responder: Mapped[ResponderProfile] = relationship(back_populates="skills")

class Availability(Base):
    __tablename__ = "availability"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    responder_id: Mapped[str] = mapped_column(ForeignKey("responder_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    responder: Mapped[ResponderProfile] = relationship(back_populates="availability")

class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    animal_category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="REPORTED", nullable=False, index=True)
    owner_organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(240), nullable=True)
    address_text: Mapped[str | None] = mapped_column(String(400), nullable=True)
    reporter_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (Index("ix_case_events_case_created", "case_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AssignmentOffer(Base):
    __tablename__ = "assignment_offers"
    __table_args__ = (UniqueConstraint("case_id", "responder_id", name="uq_case_responder_offer"), Index("ix_assignment_status_deadline", "status", "deadline_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    responder_id: Mapped[str] = mapped_column(ForeignKey("responder_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

class CaseHandoff(Base):
    __tablename__ = "case_handoffs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    from_organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    to_organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    initiated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RescueEvidence(Base):
    __tablename__ = "rescue_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    responder_id: Mapped[str] = mapped_column(ForeignKey("responder_profiles.id"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rescue_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    animal_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    rescue_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ResponderReliabilityScore(Base):
    __tablename__ = "responder_reliability_scores"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    responder_id: Mapped[str] = mapped_column(ForeignKey("responder_profiles.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    total_assignments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declined_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expired_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_response_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    score_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
