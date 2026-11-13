# ResQNet Data Model (Stage 1)

PostgreSQL is authoritative. Use UUID primary keys, `created_at`/`updated_at` in UTC, and PostGIS `geography(Point, 4326)` for coordinates. Alembic migrations will implement the physical schema in Stage 2.

## Identity and organizations

- `users`: id, email (unique), phone (nullable), password_hash (nullable for external identity), display_name, is_active, email_verified_at, created_at, updated_at, deleted_at.
- `organizations`: id, name, type (`NGO`, `SHELTER`, `VETERINARY_FACILITY`, `OTHER`), verification_status, service_description, contact details, created_at, updated_at.
- `organization_memberships`: id, organization_id, user_id, role (`COORDINATOR`, `MEMBER`), status, unique(organization_id,user_id).
- `refresh_tokens`: id, user_id, token_hash, expires_at, revoked_at, created_at.

## Responder capability

- `responders`: id, user_id, verification_status, bio, capacity, active_assignment_count, reliability_score nullable, reliability_sample_size, home/service geometry (privacy restricted), created_at, updated_at.
- `responder_skills`: id, responder_id, species_code, skill_level, verified_at.
- `service_areas`: id, responder_id, organization_id nullable, area geometry, max_travel_km, active.
- `availability`: id, responder_id, starts_at, ends_at, status, timezone, source, updated_at.

## Cases and reporting

- `cases`: id, public_tracking_token_hash, canonical_case_id nullable, status, priority, priority_source, priority_reason, triage_version, reporter_user_id, owner_organization_id, owner_user_id nullable, incident_point geography(Point,4326), public_location_label, exact_location_encrypted/controlled, species, description, incident_at, acknowledgement_due_at nullable, response_due_at nullable, version integer, created_at, updated_at, closed_at nullable, deleted_at nullable.
- `case_reports`: id, case_id, reporter_user_id, description, source (`TEXT`, `VOICE`, `PHOTO`, `FOLLOW_UP`), transcript nullable, extraction_json nullable, extraction_provider nullable, consent_record_id nullable, created_at.
- `consent_records`: id, user_id, case_id nullable, consent_type, policy_version, granted_at, withdrawn_at nullable.
- `case_events`: id, case_id, actor_user_id nullable, actor_role, event_type, from_status nullable, to_status nullable, payload_json, created_at. Append-only.

## Assignment and reliability

- `assignments`: id, case_id, responder_id, organization_id, offered_by_user_id, status (`OFFERED`, `ACCEPTED`, `REJECTED`, `EXPIRED`, `CANCELLED`, `COMPLETED`), offered_at, acknowledgement_deadline, responded_at nullable, accepted_at nullable, rejected_at nullable, rejection_reason nullable, assignment_version, created_at, updated_at.
- `escalations`: id, case_id, assignment_id nullable, reason, level, triggered_by (`SYSTEM`, `COORDINATOR`), triggered_at, next_action_due_at nullable, resolved_at nullable.
- `handoffs`: id, case_id, sending_organization_id, receiving_organization_id, requested_by_user_id, receiving_owner_user_id nullable, reason, status (`PENDING`, `ACCEPTED`, `REJECTED`, `EXPIRED`, `CANCELLED`), requested_at, deadline_at, responded_at nullable, accepted_at nullable, rejected_at nullable.

## Evidence, referrals and outcomes

- `evidence`: id, case_id, uploaded_by_user_id, object_key, original_filename, mime_type, byte_size, sha256, evidence_type, captured_at nullable, location nullable, access_classification, review_status, created_at.
- `referrals`: id, case_id, referring_organization_id, receiving_organization_id nullable, facility_name, reason, status, created_at, updated_at.
- `outcomes`: id, case_id, submitted_by_user_id, outcome_type, narrative, submitted_at, verification_status (`PENDING`, `VERIFIED`, `REJECTED`, `DISPUTED`), reviewed_by_user_id nullable, reviewed_at nullable, review_reason nullable.

## Operations and accountability

- `notifications`: id, user_id, case_id nullable, channel, event_type, payload_json, status, attempts, next_attempt_at nullable, sent_at nullable, read_at nullable, created_at.
- `jobs`: id, job_type, unique_key (unique), payload_json, run_at, status, attempts, max_attempts, locked_until nullable, last_error nullable, created_at, updated_at.
- `audit_logs`: id, actor_user_id nullable, organization_id nullable, action, resource_type, resource_id, request_id, ip_hash nullable, before_json nullable, after_json nullable, created_at. Append-only.
- `idempotency_records`: id, user_id, key, route, request_hash, response_status, response_json, expires_at, unique(user_id,key,route).

## Required constraints and indexes

- Unique normalized user email.
- Foreign keys with deliberate `RESTRICT`/`CASCADE` behavior; do not cascade-delete case history.
- Check constraints for positive capacity, nonnegative byte sizes, valid deadlines and valid enum values.
- Partial unique index: at most one assignment with status `OFFERED` or `ACCEPTED` per case (implementation may permit a short transaction overlap only if the old offer is expired first).
- Index cases by `(status, priority, created_at)`, `(owner_organization_id,status)`, `(owner_user_id,status)`, and incident time.
- GiST indexes on incident points and service-area geometry.
- Index assignment deadlines for due-offer scans; handoff deadlines for due-handoff scans; jobs `(status,run_at)`.
- Index case events `(case_id,created_at)` and audit logs `(resource_type,resource_id,created_at)`.

## Privacy note

Do not expose exact coordinates or evidence object keys through public tracking. Public endpoints return a coarse location label and a separate random tracking token, stored hashed. Exact location access is authorized and audited.
