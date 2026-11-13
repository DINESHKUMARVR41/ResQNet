from pydantic import BaseModel, Field

class ResponderProfileUpdate(BaseModel):
    species: list[str] = Field(min_length=1, max_length=12)
    service_radius_km: float = Field(ge=1, le=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capacity: int = Field(ge=1, le=10)

class AvailabilityUpdate(BaseModel):
    is_available: bool

class OfferResponse(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
