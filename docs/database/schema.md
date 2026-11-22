# Database Schema Overview

VideshaMitra uses **one schema per service**. Services never join across schemas or read another service's tables.

> **Implemented:** `core` migrations live in
> [`services/core-api/migrations`](../../services/core-api/migrations) and are
> applied by `python -m app.db.migrate` (idempotent, checksum-guarded).
> `supabase/bootstrap.sql` creates the schema roles. Local Supabase still owns
> `auth` and `storage`; a minimal stub is created by the migrations when those
> schemas are absent (CI and plain Postgres).

## `core` schema — `core-api`

- `users`: Migrant workers, caseworkers, admins
- `user_consents`: Data-processing, check-in, and WhatsApp consent history
- `idempotency_keys`: Safe retries for mutating public requests
- `outbox_events`: Transactional event outbox
- `event_dedupe`: Consumer idempotency by `event_id`
- `agencies`: Canonical SLBFE agency records and current license
- `agency_snapshots`: Dated SLBFE import batches
- `agency_license_history`: License changes across snapshots
- `verifications`: Evidence-based job/agency verification records
- `documents`: Uploaded contracts, offer letters, screenshots (metadata + storage paths)
- `migration_journeys`: Active migration stages and check-in schedule
- `checkins`: Scheduled safety check-ins and responses
- `complaints`: Complaint/case records and caseworker assignment
- `complaint_documents`: Evidence links between complaints and documents
- `case_notes`: Internal caseworker notes
- `notifications`: In-app notification feed only
- `audit_logs`: Immutable logs of sensitive worker inquiries and data accesses

`core-api` also owns the private `documents` Storage bucket and issues signed URLs.

## `ai` schema — `ai-service`

- `analysis_runs`: One row per verification analysis job
- `agent_traces`: LangGraph node/tool events for admin review
- `document_extractions`: OCR text/confidence per document page
- `chat_sessions`: Worker AI chat sessions
- `chat_messages`: Chat messages and citations
- `checkpoints`: LangGraph checkpointer state

`ai-service` fetches document bytes from `core-api`'s internal endpoint. It never reads `core.documents`.

## `notification` schema — `notification-service`

- `device_tokens`: Expo/FCM/APNs tokens, platform, app version, last seen
- `notification_preferences`: Channel opt-in and quiet hours
- `deliveries`: Delivery request per notification/channel
- `delivery_attempts`: Retry history, provider message IDs, errors
- `event_dedupe`: Consumer idempotency by `event_id`

`notification-service` receives notification content and user IDs in events. It never reads `core.users`.

## Isolation rules

- Separate database role per service: `core_api_role`, `ai_service_role`, `notification_service_role`.
- No grants across schemas.
- No cross-schema foreign keys; IDs are references only.
- Local development may use one Postgres cluster with three schemas.
- Production should use separate databases (or at minimum separate credentials and network policies).
- Each service owns its migrations under `services/<service>/migrations/`.
- Supabase CLI manages the local stack and Auth/Storage; it does not own service schemas.

## Mobile notes

- Device tokens and preferences live in `notification-service`; mobile clients register through `core-api`.
- In-app notification read state lives in `core.notifications`.
- Mobile uploads are compressed client-side and validated server-side.
- Worker-owned core tables are protected by RLS; mobile clients use the anon key plus a Supabase JWT, never the service-role key.
