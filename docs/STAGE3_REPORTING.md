# Stage 3 — Core Emergency Workflow

## Implemented

- Citizen-only case creation with server-side validation.
- Unique public case IDs and persistent case records.
- Rule-based, explainable priority suggestions (not medical diagnosis).
- Human-review flag and coordinator priority override with mandatory reason.
- Citizen-only access to their own cases; coordinator/admin access to case queue.
- Responder case browsing blocked until Stage 4 assignment exists.
- Timeline events for report submission, photograph upload and triage review.
- Optional GPS/manual location and landmark fields.
- Private image upload (JPEG/PNG/WebP, 5 MB cap, signature check, randomized filename); authenticated photo retrieval.
- Potential duplicate suggestions for same species within 1 km and 24 hours; no automatic merge.
- Frontend report form, optional browser geolocation, photo upload, citizen tracking, coordinator queue, duplicate warnings and triage review.

## API

- `POST /api/v1/cases` — citizen report.
- `GET /api/v1/cases` — own cases for citizen; queue for coordinator/admin.
- `GET /api/v1/cases/{public_id}` — authorized case details and timeline.
- `PATCH /api/v1/cases/{public_id}/triage` — coordinator/admin decision.
- `POST /api/v1/cases/{public_id}/photo` — private photo upload.
- `GET /api/v1/cases/{public_id}/photo` — authorized photo retrieval.

## Triage rules

Critical/high/medium phrase matches are transparent heuristics. No matching phrase yields `NEEDS_REVIEW`. Every new case starts in `REPORTED`, and every case requires coordinator review. The triage endpoint records the override reason and moves `REPORTED` to `TRIAGED`.

## Duplicate suggestions

Only reports with the same animal category, coordinates, and creation time within the last 24 hours are considered. The threshold is 1 km. This is a review suggestion, not a merge decision. Image similarity and semantic similarity are not implemented.

## Limitations

- AI extraction, Tamil speech transcription, image classification and speech consent flow are not implemented in Stage 3.
- Case photo storage is local filesystem storage; production needs private object storage, malware scanning, retention policy and backup.
- PostGIS geography column exists in the earlier foundation migration, but the current duplicate detector uses a portable Haversine calculation and bounded query. Dedicated PostGIS indexing/query optimization is future work.
- No assignment, deadline, escalation or handoff operations exist yet; these are Stage 4.
