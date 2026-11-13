"""AI-powered incident extraction service with deterministic fallback."""
from __future__ import annotations
import re
from typing import Optional
from pydantic import BaseModel


class IncidentExtraction(BaseModel):
    animal_category: Optional[str] = None
    animal_color: Optional[str] = None
    num_animals: Optional[int] = None
    injury_description: Optional[str] = None
    emergency_type: Optional[str] = None
    location_text: Optional[str] = None
    urgency_level: Optional[str] = None  # LOW, MEDIUM, HIGH, CRITICAL
    possible_hazards: list[str] = []
    missing_info: list[str] = []
    confidence_score: float = 0.0
    needs_human_review: bool = True
    suggested_priority: str = "NEEDS_REVIEW"
    explanation: str = ""
    source: str = "deterministic"


# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------
ANIMAL_KEYWORDS: dict[str, list[str]] = {
    "dog": ["dog", "puppy", "pup", "canine", "hound"],
    "cat": ["cat", "kitten", "feline"],
    "cow": ["cow", "bull", "calf", "cattle", "bovine", "ox"],
    "bird": ["bird", "pigeon", "parrot", "crow", "owl", "eagle", "hen", "rooster"],
    "snake": ["snake", "cobra", "viper", "python", "reptile", "serpent"],
    "monkey": ["monkey", "ape", "macaque", "langur"],
    "rat": ["rat", "mouse", "rodent"],
    "deer": ["deer", "stag", "fawn"],
    "horse": ["horse", "pony", "mule", "donkey"],
    "elephant": ["elephant"],
    "squirrel": ["squirrel"],
    "rabbit": ["rabbit", "bunny", "hare"],
}

CRITICAL_KEYWORDS = [
    "bleeding", "blood", "bleed", "unconscious", "dying", "dead", "broken leg",
    "hit by vehicle", "hit by car", "hit by truck", "accident", "crushed", "severe injury",
    "not breathing", "choking", "drowning", "trapped", "fire", "burning", "electrocuted",
    "injured badly", "badly injured", "critical", "emergency", "attack", "attacked",
    "mauled", "fracture", "fractures",
]
HIGH_KEYWORDS = [
    "injured", "wound", "wounds", "limping", "can't move", "cannot move", "unable to move",
    "in pain", "crying", "howling", "screaming", "dehydrated", "starving", "malnourished",
    "abandoned", "lost", "distressed", "entangled", "stuck", "stranded",
]
HAZARD_KEYWORDS = {
    "traffic": ["road", "highway", "traffic", "vehicle", "car", "bus", "truck"],
    "water": ["river", "flood", "drowning", "water", "lake", "pond", "drain"],
    "electrical": ["electrocuted", "electric", "wire", "current"],
    "fire": ["fire", "burning", "smoke"],
    "aggressive animal": ["aggressive", "biting", "violent", "dangerous"],
}

COLOR_KEYWORDS = ["black", "white", "brown", "grey", "gray", "golden", "orange", "spotted",
                  "striped", "yellow", "cream", "tan", "red"]


def _deterministic_extract(text: str) -> IncidentExtraction:
    lower = text.lower()

    # Animal detection
    animal_category = None
    for animal, keywords in ANIMAL_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            animal_category = animal
            break

    # Color detection
    animal_color = next((c for c in COLOR_KEYWORDS if c in lower), None)

    # Num animals (simple: look for digit + animal)
    num_animals = None
    m = re.search(r"\b(\d+)\s*(dogs?|cats?|cows?|birds?|snakes?|animals?)\b", lower)
    if m:
        num_animals = int(m.group(1))

    # Injury description
    injury_words = [kw for kw in CRITICAL_KEYWORDS + HIGH_KEYWORDS if kw in lower]
    injury_description = ", ".join(injury_words[:5]) if injury_words else None

    # Emergency type
    if any(kw in lower for kw in ["hit by", "accident", "collision"]):
        emergency_type = "road_accident"
    elif any(kw in lower for kw in ["fire", "burning"]):
        emergency_type = "fire"
    elif any(kw in lower for kw in ["drowning", "flood", "river"]):
        emergency_type = "water"
    elif any(kw in lower for kw in ["trapped", "stuck", "entangled"]):
        emergency_type = "entrapment"
    elif any(kw in lower for kw in ["abandoned", "lost"]):
        emergency_type = "abandonment"
    else:
        emergency_type = "general_rescue"

    # Location text — look for "near", "at", "in" followed by capitalized words
    location_text = None
    loc_match = re.search(r"\b(?:near|at|in|beside|behind|front of)\s+([A-Za-z0-9 ,]{3,60})", text)
    if loc_match:
        location_text = loc_match.group(1).strip()

    # Urgency / priority
    if any(kw in lower for kw in CRITICAL_KEYWORDS):
        urgency_level = "CRITICAL"
        suggested_priority = "CRITICAL"
    elif any(kw in lower for kw in HIGH_KEYWORDS):
        urgency_level = "HIGH"
        suggested_priority = "HIGH"
    else:
        urgency_level = "MEDIUM"
        suggested_priority = "MEDIUM"

    # Hazards
    possible_hazards = [hazard for hazard, kws in HAZARD_KEYWORDS.items() if any(k in lower for k in kws)]

    # Missing info
    missing_info = []
    if not animal_category:
        missing_info.append("animal type not specified")
    if not location_text:
        missing_info.append("precise location unclear")
    if not injury_description:
        missing_info.append("injury details not described")

    # Confidence
    hits = int(bool(animal_category)) + int(bool(location_text)) + int(bool(injury_description))
    confidence_score = round(0.4 + hits * 0.15, 2)

    needs_human_review = confidence_score < 0.7 or not animal_category

    explanation = (
        f"Deterministic extraction. Animal: {animal_category or 'unknown'}. "
        f"Urgency: {urgency_level}. Hazards: {possible_hazards or 'none'}. "
        f"Confidence: {confidence_score:.0%}."
    )

    return IncidentExtraction(
        animal_category=animal_category,
        animal_color=animal_color,
        num_animals=num_animals,
        injury_description=injury_description,
        emergency_type=emergency_type,
        location_text=location_text,
        urgency_level=urgency_level,
        possible_hazards=possible_hazards,
        missing_info=missing_info,
        confidence_score=confidence_score,
        needs_human_review=needs_human_review,
        suggested_priority=suggested_priority,
        explanation=explanation,
        source="deterministic",
    )


def _gemini_extract(text: str) -> Optional[IncidentExtraction]:
    """Call Gemini API for structured extraction. Returns None on any failure."""
    try:
        from app.core.config import settings
        if not settings.gemini_api_key:
            return None
        import httpx, json
        prompt = (
            "You are an expert animal rescue triage assistant. Extract structured information "
            "from the following incident report and respond ONLY with a JSON object matching "
            "these fields: animal_category (str), animal_color (str|null), num_animals (int|null), "
            "injury_description (str|null), emergency_type (str), location_text (str|null), "
            "urgency_level (one of LOW/MEDIUM/HIGH/CRITICAL), possible_hazards (list[str]), "
            "missing_info (list[str]), confidence_score (float 0-1), needs_human_review (bool), "
            "suggested_priority (one of LOW/MEDIUM/HIGH/CRITICAL/NEEDS_REVIEW), explanation (str).\n\n"
            f"Incident report: {text}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        with httpx.Client(timeout=15) as client:
            r = client.post(url, json=payload)
        if r.status_code != 200:
            return None
        raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown code fences if present
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()
        data = json.loads(raw_text)
        data["source"] = "gemini"
        return IncidentExtraction(**data)
    except Exception:
        return None


def extract_incident(text: str) -> IncidentExtraction:
    """Public entry point: try Gemini first, fall back to deterministic."""
    result = _gemini_extract(text)
    if result is not None:
        return result
    return _deterministic_extract(text)
