# ResQNet API Contract (Stage 1)

Base path: `/api/v1`. JSON over HTTPS. All timestamps are ISO-8601 UTC. Authenticated endpoints use `Authorization: Bearer <access_token>`.

## Authentication

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| POST | `/auth/register` | Create citizen account | Public, rate-limited |
| POST | `/auth/login` | Obtain access/refresh tokens | Public, rate-limited |
| POST | `/auth/refresh` | Rotate refresh token | Refresh token |
| POST | `/auth/logout` | Revoke refresh token | Authenticated |
| GET | `/auth/me` | Current user and memberships | Authenticated |

## Citizen and case reporting

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| POST | `/reports/assist` | Extract structured fields from text/audio metadata; advisory only | Authenticated citizen |
| POST | `/cases` | Create confirmed report and case | Authenticated citizen |
| GET | `/cases/{case_id}/tracking` | Privacy-filtered tracking view | Reporter / authorized parties / public token |
| POST | `/cases/{case_id}/reports` | Add information to existing case | Reporter / authorized parties |
| GET | `/cases/{case_id}` | Case details | Scoped roles |
| GET | `/cases/{case_id}/events` | Timeline | Scoped roles |

## Coordination and triage

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| POST | `/cases/{case_id}/triage` | Run deterministic triage | Coordinator |
| PATCH | `/cases/{case_id}/priority` | Override priority with mandatory reason | Coordinator |
| GET | `/cases/{case_id}/duplicates` | Candidate duplicate reports | Coordinator |
| POST | `/cases/{case_id}/duplicates/{candidate_id}/merge` | Confirm merge | Coordinator |
| GET | `/cases` | Filtered case queue | Coordinator / admin |
| GET | `/dashboard/operations` | Database-derived operational metrics | Coordinator / admin |

## Responders and assignments

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| GET/PUT | `/responders/me` | Responder profile | Rescuer |
| PUT | `/responders/me/availability` | Availability/capacity | Rescuer |
| GET | `/cases/{case_id}/recommendations` | Eligible, ranked responders with explanations | Coordinator |
| POST | `/cases/{case_id}/assignments` | Create time-limited offer | Coordinator |
| POST | `/assignments/{assignment_id}/accept` | Accept offer | Offered responder |
| POST | `/assignments/{assignment_id}/reject` | Reject with reason | Offered responder |
| POST | `/assignments/{assignment_id}/arrive` | Record arrival and location | Assigned responder |
| POST | `/assignments/{assignment_id}/progress` | Record travel/assistance progress | Assigned responder |
| POST | `/cases/{case_id}/escalate` | Manual escalation | Coordinator / admin |

## Handoffs, evidence and outcomes

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| POST | `/cases/{case_id}/handoffs` | Request organization/facility handoff | Current owner |
| POST | `/handoffs/{handoff_id}/accept` | Explicitly accept transfer | Receiving coordinator |
| POST | `/handoffs/{handoff_id}/reject` | Reject with reason | Receiving coordinator |
| POST | `/cases/{case_id}/evidence` | Upload evidence metadata/file | Authorized case participant |
| POST | `/cases/{case_id}/outcomes` | Submit outcome for review | Assigned responder |
| POST | `/outcomes/{outcome_id}/verify` | Verify or reject outcome | Coordinator |
| POST | `/cases/{case_id}/reopen` | Reopen with reason | Coordinator / admin |

## Notifications, admin and health

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| GET | `/notifications` | Current user's notifications | Authenticated |
| POST | `/notifications/{id}/read` | Mark notification read | Owner |
| GET | `/admin/audit-logs` | Search audit records | Admin |
| GET | `/admin/organizations` | Organization administration | Admin |
| GET | `/health/live` | Process liveness | Public |
| GET | `/health/ready` | DB and dependency readiness | Public/internal |

## Error envelope

```json
{
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "message": "A case in OFFERED cannot move directly to CLOSED.",
    "details": {"current_state": "OFFERED", "requested_state": "CLOSED"},
    "request_id": "..."
  }
}
```

Use HTTP 401 for unauthenticated, 403 for unauthorized, 404 for inaccessible/not-found resources (avoid leaking existence), 409 for state/concurrency conflicts, 422 for validation errors, 429 for rate limits and 5xx for unexpected failures.

## Idempotency and concurrency

Mutating endpoints that can be retried (`POST /cases`, assignment acceptance, handoff acceptance, evidence/outcome submission) accept an `Idempotency-Key`. State changes use a transaction and row lock on the case. Assignment creation also checks a partial unique constraint for one active assignment per case. Deadline jobs carry a unique job key per assignment/deadline version.

## Stage 3 case reporting endpoints

All endpoints below are under `/api/v1` and require a bearer token unless noted otherwise.

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/cases` | Citizen | Submit a confirmed report |
| GET | `/cases` | Citizen / coordinator / admin | Own reports or coordinator queue |
| GET | `/cases/{public_id}` | Owner / coordinator / admin | Case details and event timeline |
| PATCH | `/cases/{public_id}/triage` | Coordinator / admin | Record priority and mandatory override reason |
| POST | `/cases/{public_id}/photo` | Owner / coordinator / admin | Upload private JPEG/PNG/WebP image, max 5 MB |
| GET | `/cases/{public_id}/photo` | Owner / coordinator / admin | Authenticated photo retrieval |

A citizen can only see cases they reported. Responders cannot browse the queue before assignment functionality is implemented in Stage 4. A report always starts in `REPORTED`; only coordinator/admin triage can move it to `TRIAGED`. Duplicate matching is advisory and never merges or deletes a case.

## Stage 4 — Rescue Reliability Engine

- `GET/PUT /responders/me/profile` — responder reads/updates species, service radius, capacity and coordinates.
- `PATCH /responders/me/availability` — responder availability toggle; only verified responders can go available.
- `PATCH /admin/responders/{user_id}/verify` — admin verification.
- `GET /coordinator/cases/{public_id}/eligible-responders` — coordinator-only explainable eligibility/ranking list.
- `POST /coordinator/cases/{public_id}/assign` — issue a two-minute offer to the best eligible responder.
- `GET /responder/offers` — responder's pending and historical offers.
- `POST /responder/offers/{offer_id}/accept|decline` — only the offer recipient may respond; decline reason is audited.
- `PATCH /responder/cases/{public_id}/status` — accepted responder moves case through `IN_PROGRESS` then `ON_SCENE`.
- `POST /coordinator/cases/{public_id}/handoffs` — request a ten-minute handoff to a verified organization. Current owner remains unchanged until acceptance.
- `POST /coordinator/handoffs/{handoff_id}/accept|decline` — receiving organization's coordinator (or admin) responds.
- `POST /jobs/process-deadlines` — admin-only manual deadline sweep; background worker also runs every five seconds.

Assignment offers, responder responses, deadline expiry, and handoff decisions are persisted and reflected in the case event timeline.
