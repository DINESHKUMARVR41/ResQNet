"""Transparent keyword triage. This is not medical diagnosis."""
CRITICAL_TERMS = ("unconscious", "not breathing", "heavy bleeding", "severe bleeding", "hit by vehicle", "road accident", "trapped", "severely injured")
HIGH_TERMS = ("bleeding", "fracture", "broken leg", "unable to walk", "burn", "poison", "poisoned", "wound", "deep cut")
MEDIUM_TERMS = ("limping", "weak", "sick", "injured", "stranded", "abandoned", "stuck")

def suggest_priority(description: str) -> tuple[str, str, float, bool]:
    text = description.casefold()
    for terms, priority, confidence, reason in [
        (CRITICAL_TERMS, "CRITICAL", 0.88, "Description contains a potentially life-threatening emergency indicator."),
        (HIGH_TERMS, "HIGH", 0.78, "Description contains an indicator requiring prompt human assessment."),
        (MEDIUM_TERMS, "MEDIUM", 0.65, "Description indicates an animal may need assistance."),
    ]:
        matches = [term for term in terms if term in text]
        if matches:
            return priority, f"{reason} Matched phrase(s): {', '.join(matches)}. This is a rule-based suggestion, not a diagnosis.", confidence, True
    return "NEEDS_REVIEW", "No configured emergency phrase matched. A coordinator should review the report before prioritization.", 0.0, True
