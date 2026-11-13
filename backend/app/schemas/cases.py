from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class CaseCreate(BaseModel):
    animal_category: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=10, max_length=5000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    landmark: str | None = Field(default=None, max_length=240)
    address_text: str | None = Field(default=None, max_length=400)
    reporter_phone: str | None = Field(default=None, max_length=30)

class TriageUpdate(BaseModel):
    priority: str = Field(pattern="^(CRITICAL|HIGH|MEDIUM|LOW|NEEDS_REVIEW)$")
    reason: str = Field(min_length=8, max_length=1000)

class CaseEventRead(BaseModel):
    id: str
    event_type: str
    from_status: str | None
    to_status: str | None
    message: str
    created_at: datetime
    actor_name: str | None = None

class CaseRead(BaseModel):
    id: str
    public_id: str
    reporter_id: str
    animal_category: str
    description: str
    status: str
    priority: str
    latitude: float | None
    longitude: float | None
    landmark: str | None
    address_text: str | None
    reporter_phone: str | None
    ai_summary: str | None
    triage_reason: str | None
    triage_confidence: float | None
    needs_human_review: bool
    has_photo: bool
    created_at: datetime
    updated_at: datetime
    possible_duplicates: list[dict] = []
    events: list[CaseEventRead] = []
    model_config = ConfigDict(from_attributes=True)
