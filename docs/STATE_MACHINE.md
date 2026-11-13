# ResQNet Case State Machine

## State meanings

| State | Meaning |
|---|---|
| `REPORTED` | Citizen submitted a confirmed report; no triage completed yet |
| `TRIAGED` | Rules-based triage completed; awaiting an offer/coordination action |
| `OFFERED` | At least one responder has an active time-limited offer; not accepted |
| `ACCEPTED` | A responder explicitly accepted and is the accountable assignee |
| `EN_ROUTE` | Responder recorded departure/travel |
| `ON_SITE` | Responder recorded arrival; arrival evidence/time is stored |
| `TREATED` | Assistance was recorded; this is not yet verified closure |
| `TRANSPORTED` | Animal transport was recorded; destination/referral is stored |
| `PENDING_VERIFICATION` | Outcome and required evidence submitted for coordinator review |
| `CLOSED` | Authorized coordinator verified the outcome |
| `ESCALATED` | Reliability deadline was missed or coordinator escalated; ownership remains explicit |
| `UNRESOLVED_HANDOFF` | A handoff is pending or failed; sending organization remains accountable |
| `DISPUTED` | Evidence/outcome is contested; coordinator review required |
| `REOPENED` | Previously closed case reopened with reason and new owner/action |
| `DUPLICATE_MERGED` | Coordinator confirmed this report is represented by another canonical case |
| `FLAGGED_FALSE` | Authorized reviewer flagged report as false with reason; not a silent deletion |

## Allowed transitions (initial policy)

- `REPORTED -> TRIAGED | FLAGGED_FALSE | DUPLICATE_MERGED`
- `TRIAGED -> OFFERED | ESCALATED | FLAGGED_FALSE | DUPLICATE_MERGED`
- `OFFERED -> ACCEPTED | ESCALATED | TRIAGED`
- `ACCEPTED -> EN_ROUTE | ESCALATED | UNRESOLVED_HANDOFF`
- `EN_ROUTE -> ON_SITE | ESCALATED | UNRESOLVED_HANDOFF`
- `ON_SITE -> TREATED | TRANSPORTED | PENDING_VERIFICATION | UNRESOLVED_HANDOFF | DISPUTED`
- `TREATED -> TRANSPORTED | PENDING_VERIFICATION | DISPUTED`
- `TRANSPORTED -> PENDING_VERIFICATION | UNRESOLVED_HANDOFF | DISPUTED`
- `PENDING_VERIFICATION -> CLOSED | DISPUTED | REOPENED`
- `ESCALATED -> OFFERED | ACCEPTED | UNRESOLVED_HANDOFF | DISPUTED`
- `UNRESOLVED_HANDOFF -> ACCEPTED | ESCALATED | DISPUTED`
- `CLOSED -> REOPENED | DISPUTED`
- `DISPUTED -> PENDING_VERIFICATION | REOPENED | CLOSED`
- `REOPENED -> TRIAGED | OFFERED | ESCALATED`
- `DUPLICATE_MERGED` and `FLAGGED_FALSE` are terminal except an audited admin correction/reopen procedure.

## Transition authorization

- Citizen: create report; add information; view permitted tracking projection.
- Rescuer: accept/reject own offer; update own assignment travel/arrival/assistance; submit evidence/outcome; request handoff.
- NGO coordinator: triage, offer/assign/reassign, escalate, accept/reject inbound handoff, verify outcome, dispute/reopen, merge duplicate.
- Admin: all coordinator operations plus user/org administration; every privileged action audited.

## Important distinction

`OFFERED` means an invitation was sent. `ACCEPTED` means a responder took responsibility. `ON_SITE` means arrival was recorded. `PENDING_VERIFICATION` means the responder submitted an outcome. Only `CLOSED` means a coordinator verified it.

The `ESCALATED` state is an operational flag/state, not permission to discard or detach the current owner. Escalation must create an event and a next action/deadline.

## Stage 4 implementation mapping

The Stage 4 code currently implements these operational states (the more detailed care/outcome states above remain future workflow design):

- `REPORTED` → `TRIAGED` (coordinator review)
- `TRIAGED` → `ASSIGNMENT_PENDING` (time-limited responder offer; not yet accepted)
- `ASSIGNMENT_PENDING` → `ASSIGNED` (responder explicitly accepts)
- `ASSIGNMENT_PENDING` → `NEEDS_COORDINATOR` (all eligible responders declined/expired or no eligible candidate remains)
- `ASSIGNED` → `IN_PROGRESS` → `ON_SCENE` (accepted responder records progress)

An organization handoff has its own persisted `PENDING` / `ACCEPTED` / `DECLINED` / `EXPIRED` lifecycle. The current owner remains unchanged until the receiving organization explicitly accepts. Full care outcome, evidence verification and closure are intentionally deferred to later stages.
