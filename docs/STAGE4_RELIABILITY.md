# ResQNet Stage 4 — Rescue Reliability Engine

## What Stage 4 adds

Stage 4 converts a triaged report into an accountable response workflow. Assignment is not considered complete when a notification/offer is sent; the selected responder must explicitly accept it.

### Responder eligibility and ranking

A candidate must satisfy all hard checks:
- User is active and verified; responder profile has an admin-set verification timestamp.
- Responder has an exact species skill or the `all` skill.
- Responder is marked available.
- If the incident has coordinates, responder coordinates must exist and the incident must fall within the configured service radius.
- Number of accepted, still-open assignments must be below the responder's capacity.
- A responder who has already received an offer for the same case is not offered that case again.

Eligible responders are ranked by straight-line Haversine distance (closest first). The score is transparent (`100 - 2 × distance_km`, or 50 when the report has no coordinates); it is a ranking score, not a probability or guarantee of response time.

### Offer lifecycle

1. Coordinator reviews/triages a case.
2. Coordinator requests assignment. ResQNet creates one persisted offer for the highest-ranked eligible responder.
3. Offer has a two-minute acknowledgement deadline.
4. Responder can accept or decline with a reason. Acceptance changes the case to `ASSIGNED` and creates an audit event. Decline triggers the next eligible responder.
5. A background database worker checks every five seconds. An expired offer is marked `EXPIRED` and the next eligible responder is offered the case. If no candidates remain, the case becomes `NEEDS_COORDINATOR` and remains open.
6. An accepted responder can move the case sequentially from `ASSIGNED` → `IN_PROGRESS` → `ON_SCENE`. Responders cannot mark a rescue completed in Stage 4; outcome evidence and coordinator verification belong to a later stage.

### Organization handoff ownership

A coordinator can request a handoff to a verified organization. The current organization remains the owner while the request is pending. Only a coordinator associated with the receiving organization (or an admin) can accept it. Ownership changes only after explicit acceptance. Declined or expired handoffs leave ownership unchanged. The handoff deadline is ten minutes.

### Key endpoints

| Method | Endpoint | Access |
|---|---|---|
| GET/PUT | `/api/v1/responders/me/profile` | Responder |
| PATCH | `/api/v1/responders/me/availability` | Responder |
| PATCH | `/api/v1/admin/responders/{user_id}/verify` | Admin |
| GET | `/api/v1/coordinator/cases/{public_id}/eligible-responders` | Coordinator/Admin |
| POST | `/api/v1/coordinator/cases/{public_id}/assign` | Coordinator/Admin |
| GET | `/api/v1/responder/offers` | Responder |
| POST | `/api/v1/responder/offers/{offer_id}/accept` | Offer recipient |
| POST | `/api/v1/responder/offers/{offer_id}/decline` | Offer recipient |
| PATCH | `/api/v1/responder/cases/{public_id}/status` | Accepted responder |
| POST | `/api/v1/jobs/process-deadlines` | Admin manual fallback |
| POST | `/api/v1/coordinator/cases/{public_id}/handoffs` | Current owner coordinator/Admin |
| POST | `/api/v1/coordinator/handoffs/{handoff_id}/accept` | Receiving coordinator/Admin |
| POST | `/api/v1/coordinator/handoffs/{handoff_id}/decline` | Receiving coordinator/Admin |

### Demo setup

The synthetic Salem responder is seeded as verified, available, skilled for dogs and cats, with a 20 km service radius and demo coordinates. Demo coordinator is linked to the demo Salem NGO. Demo credentials remain `ResQNetDemo!2026`.

### Limitations and production hardening

- The deadline worker is a single-process FastAPI background task with a manual admin fallback. For multiple API replicas, move it to a dedicated worker/queue and use database row locks/atomic claims. SQLite is for local development; production should use PostgreSQL.
- Ranking uses straight-line distance, not road travel time. Operating-hour calendars, responder schedules, push notifications/SMS, and live GPS are not connected.
- Organization coordinator membership is represented by one `users.organization_id` association; production needs invitation/approval and multi-member organization roles.
- Handoff is implemented at organization ownership level. It does not yet transfer individual responder assignments or external NGO case-management records.
- No real emergency service is contacted. Demo users and locations are synthetic.
