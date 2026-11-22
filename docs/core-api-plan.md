# Core API — Implementation Plan (Microservices)

> Companion to [`docs/architecture/microservices.md`](architecture/microservices.md).
>
> **Scope:** `services/core-api` only. `ai-service` and `notification-service` are separate deployables with separate schemas. This plan does not implement their internals; `notification-service` is also owned by Person 1, while `ai-service` belongs to Person 2.
>
> **Owner:** Person 1. **Public entry point:** Kong → `core-api`. No client talks to the other services directly.
>
> **Progress:** track execution in [`docs/progress.md`](progress.md). Update it after every run.

---

## 1. Mission

`core-api` is the transactional heart of VideshaMitra and the only public backend.

It must:

- Authenticate workers, caseworkers, and admins via Supabase Auth.
- Own users, consents, agencies, verification records, document metadata, journeys, check-ins, complaints/cases, in-app notifications, audit logs, and admin APIs.
- Orchestrate AI work asynchronously without owning AI implementation details.
- Publish notification requests without owning delivery channels or device tokens.
- Provide a stable OpenAPI contract for the worker web app, admin portal, and mobile app.
- Keep all transactional data consistent in one database and one service.

It must not:

- Run LangGraph, OCR, LLM calls, speech models, or chat sessions.
- Store Expo/FCM/WhatsApp tokens, notification preferences, or delivery attempts.
- Join across the `ai` or `notification` schemas.
- Allow clients to call internal services directly.

---

## 2. Service boundaries

| Capability | `core-api` | `ai-service` | `notification-service` |
|---|---|---|---|
| Auth, users, consents | **Owns** | — | — |
| Agencies, SLBFE imports, license history | **Owns** | — | — |
| Verification records and orchestration | **Owns** | Consumes request, returns result | — |
| Document metadata + storage | **Owns** | Reads content via internal endpoint | — |
| OCR text, AI traces, LangGraph checkpoints | — | **Owns** | — |
| Journeys, check-ins, scheduling | **Owns** | — | — |
| Complaints, cases, case notes | **Owns** | — | — |
| In-app notification feed | **Owns** | — | — |
| Device tokens, preferences, delivery | Proxies device/preferences API | — | **Owns** |
| Chat, speech | Authenticates + proxies | **Owns** | — |
| Admin dashboard/case review | **Owns** | Provides traces on request | — |
| Audit logs | **Owns** | Own logs only | Own logs only |

Complaints/cases are intentionally part of `core-api`: they are transactional, tightly coupled to check-ins and verifications, and drive the admin portal. They are not AI or delivery concerns.

Check-in scheduling and the agency license watchdog are also `core-api` workers. The AI service provides guardian guidance and risk triage; it does not own scheduling or license monitoring.

Rules:

1. `core-api` and the other services reference each other by IDs only.
2. No cross-schema SQL, no cross-service foreign keys, no shared ORM models.
3. Long-running work goes through Redis Streams, not synchronous HTTP.
4. Internal HTTP is only for fast calls or streaming (chat/speech/device preferences/traces).
5. Public API changes go through `core-api`'s OpenAPI.

---

## 3. Target repository layout

```
videshamitra-platform/
├── services/
│   ├── core-api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   │   ├── v1/                 # public routes
│   │   │   │   └── internal/           # service-to-service routes
│   │   │   ├── core/                   # config, security, errors, logging
│   │   │   ├── db/                     # asyncpg pool, transactions, migrations
│   │   │   ├── models/                 # domain dataclasses/enums
│   │   │   ├── repositories/           # SQL per aggregate
│   │   │   ├── services/               # business logic
│   │   │   ├── schemas/                # Pydantic DTOs
│   │   │   ├── workers/                # outbox, AI results, scheduler, watchdog
│   │   │   ├── integrations/           # AI client, notification client, SLBFE, storage
│   │   │   └── events/                 # contracts, publisher, consumer
│   │   ├── migrations/                 # core schema only
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── ai-service/                     # Person 2
│   └── notification-service/           # Person 1
├── packages/contracts/                 # shared event JSON schemas + generated models
├── admin-frontend/
├── web-frontend/
├── supabase/                           # local Supabase config + auth/storage bootstrap
├── infra/
├── docs/
├── docker-compose.yml
└── .github/
```

**First migration step:** move the current `web-backend/` scaffold to `services/core-api/`. Do not keep two backend trees.

---

## 4. Locked decisions

| # | Decision | Choice |
|---|---|---|
| C1 | Data access | `asyncpg` pool + explicit SQL in repositories; migrations are the schema source of truth |
| C2 | Public auth | Supabase Auth; `core-api` verifies access tokens |
| C3 | Internal auth | Short-lived service JWT (`iss`, `aud`, `sub`, `exp`) |
| C4 | Event bus | Redis Streams + transactional outbox |
| C5 | Event delivery | At-least-once; every consumer dedupes by `event_id` |
| C6 | AI execution | Async jobs; no OCR/LLM in the request path |
| C7 | Notifications | `core-api` owns the in-app feed; `notification-service` owns delivery |
| C8 | Document access | AI-service fetches bytes from `core-api` internal endpoint |
| C9 | Chat | `core-api` authenticates and proxies SSE to `ai-service` |
| C10 | Databases | `core` schema locally; separate database recommended in production |
| C11 | Public API | Only `core-api`; internal services have no Kong routes |
| C12 | Consistency | No distributed transactions; outbox + idempotency + retries |

---

## 5. Core database schema

### Schema and roles

- Schema: `core`.
- Role: `core_api_role` with grants only on `core`.
- Separate roles: `ai_service_role` (owns `ai`), `notification_service_role` (owns `notification`).
- No role may read another service's schema.
- Supabase Auth owns `auth`; Supabase Storage owns `storage`.
- Migrations live in `services/core-api/migrations/` and are applied by the core migration runner.

### Migration order

| File | Contents |
|---|---|
| `001_core_foundation.sql` | extensions, enums, `users`, `user_consents`, `idempotency_keys`, `outbox_events`, `event_dedupe`, triggers |
| `002_agencies.sql` | `agency_snapshots`, `agencies`, `agency_license_history`, trigram indexes |
| `003_verifications_documents.sql` | `verifications`, `documents` |
| `004_journeys_checkins.sql` | `migration_journeys`, `checkins` |
| `005_complaints_cases.sql` | `complaints`, `complaint_documents`, `case_notes` |
| `006_notifications.sql` | `notifications` (in-app feed only) |
| `007_audit.sql` | `audit_logs` |
| `008_rls.sql` | RLS policies, helper functions |
| `009_storage.sql` | documents bucket + storage policies |
| `010_indexes.sql` | composite/partial indexes not defined inline |

### Enums

```text
user_role: worker | caseworker | admin
language_code: en | si | ta
consent_type: data_processing | checkins | whatsapp
agency_license_status: active | suspended | expired | cancelled | unknown
verification_status: pending | processing | verified | suspicious | fraudulent | failed
risk_level: low | medium | high | critical
document_type: job_offer | employment_contract | passport | visa | payment_receipt | screenshot | other
document_status: uploaded | processing | processed | failed
journey_stage: pre_departure | employed_abroad | returned
checkin_status: scheduled | sent | completed | missed | escalated
complaint_status: draft | submitted | under_review | escalated | resolved | closed
notification_type: checkin_due | checkin_missed | agency_license_changed | verification_complete | complaint_update | caseworker_message | system
notification_channel: in_app | push | whatsapp | email | sms
```

`delivery_status` and `device_platform` belong to `notification-service`, not here.

### Tables

General rules (unless noted):

- `id uuid primary key default gen_random_uuid()`
- `created_at timestamptz not null default now()`
- mutable tables have `updated_at` maintained by a trigger
- user-owned rows cascade on user deletion where appropriate

#### `users`

`id` (references `auth.users`), `role`, `full_name`, `phone`, `preferred_language`, `country_of_work`, `is_active`, `created_at`, `updated_at`.

Triggers:

- On `auth.users` insert → create `core.users` row with `role = 'worker'`.
- Prevent self-service changes to `role`/`is_active`.

#### `user_consents`

`id`, `user_id`, `type`, `granted`, `version`, `granted_at`, `revoked_at`, `ip_address`, `user_agent`.

#### `idempotency_keys`

`id`, `user_id`, `key`, `method`, `path`, `request_hash`, `status_code`, `response_body jsonb`, `created_at`, `expires_at`. Unique `(user_id, key)`.

#### `outbox_events`

`id`, `event_id` unique, `event_type`, `version`, `stream`, `payload jsonb`, `status` (`pending|published|failed`), `attempts`, `available_at`, `created_at`, `published_at`, `last_error`.

Index: `(status, available_at)`.

#### `event_dedupe`

`id`, `consumer`, `event_id`, `processed_at`. Unique `(consumer, event_id)`.

#### `agency_snapshots`

`id`, `snapshot_date`, `source_url`, `checksum`, `record_count`, `imported_by`, `imported_at`. Unique `(snapshot_date, checksum)`.

#### `agencies`

`id`, `registration_no` unique, `name`, `normalized_name`, `license_no`, `license_status`, `license_expires_on`, `address`, `district`, `phone`, `email`, `latest_snapshot_id`, `created_at`, `updated_at`.

Indexes:

```sql
create index agencies_name_trgm_idx on core.agencies using gin (normalized_name gin_trgm_ops);
create index agencies_license_status_idx on core.agencies (license_status);
create index agencies_district_idx on core.agencies (district);
```

#### `agency_license_history`

`id`, `agency_id`, `snapshot_id`, `license_no`, `status`, `issued_on`, `expires_on`, `job_categories text[]`, `raw_data jsonb`, `created_at`. Unique `(agency_id, snapshot_id, license_no)`.

#### `verifications`

`id`, `user_id`, `agency_id`, `agency_name_input`, `job_title`, `employer_name`, `destination_country`, `offered_salary numeric`, `currency`, `status`, `risk_level`, `risk_score`, `findings jsonb`, `evidence jsonb`, `engine_version`, `analysis_run_id`, `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`, `completed_at`.

Indexes: `(user_id, created_at desc)`, `(status)`, `(risk_level)`.

#### `documents`

`id`, `user_id`, `verification_id`, `type`, `status`, `storage_path`, `original_filename`, `mime_type`, `size_bytes`, `page_count`, `sha256`, `metadata jsonb`, `created_at`, `updated_at`, `deleted_at`.

Indexes: `(user_id, created_at desc)`, `(verification_id)`, `(sha256)`, `(deleted_at)`.

OCR text and extraction results are owned by `ai-service`, not stored here.

#### `migration_journeys`

`id`, `user_id`, `agency_id`, `destination_country`, `employer_name`, `job_title`, `departure_date`, `return_date`, `stage`, `consent_checkins`, `consent_at`, `next_checkin_at`, `created_at`, `updated_at`.

Indexes: `(user_id)`, `(stage)`, `(next_checkin_at)`.

#### `checkins`

`id`, `journey_id`, `user_id`, `due_at`, `channel`, `status`, `sent_at`, `completed_at`, `response jsonb`, `risk_level`, `created_at`, `updated_at`.

Indexes: `(journey_id)`, `(status, due_at)`, `(user_id, created_at desc)`.

#### `complaints`

`id`, `user_id`, `journey_id`, `verification_id`, `agency_id`, `checkin_id`, `title`, `description`, `status`, `triage_tier`, `assigned_to`, `evidence jsonb`, `draft_text`, `submitted_at`, `resolved_at`, `created_at`, `updated_at`.

Indexes: `(user_id, created_at desc)`, `(status)`, `(assigned_to)`, `(triage_tier)`.

#### `complaint_documents`

`complaint_id`, `document_id`, `created_at`. Primary key `(complaint_id, document_id)`.

#### `case_notes`

`id`, `complaint_id`, `author_id`, `body`, `is_internal`, `created_at`.

#### `notifications`

In-app feed only: `id`, `user_id`, `type`, `title`, `body`, `data jsonb`, `deep_link`, `read_at`, `created_at`.

Indexes: `(user_id, created_at desc)`, `(user_id, read_at)`.

No device tokens, preferences, or delivery records here.

#### `audit_logs`

`id`, `actor_id`, `actor_role`, `action`, `entity_type`, `entity_id`, `ip_address`, `user_agent`, `metadata jsonb`, `created_at`.

Indexes: `(actor_id)`, `(entity_type, entity_id)`, `(created_at desc)`.

### RLS and storage

- Enable RLS on all core tables.
- Helpers: `core.current_user_role()`, `core.is_staff()`, `core.is_admin()` (`security definer`, fixed `search_path`).
- Workers read/update only their rows; staff read all; admin manages roles/agencies/audit.
- `notifications` and `device`-related tables have no cross-service policies.
- Storage bucket `documents` is private; path `{user_id}/{document_id}/{filename}`.
- Workers can access only their path; staff read via signed URLs issued by `core-api`.
- Backend uses a trusted DB role and enforces authorization in services; RLS is defense-in-depth for direct Supabase access.

### Seed data

- 1 admin, 2 caseworkers, 3 workers.
- 4 agencies: active, suspended, expired, license mismatch.
- 2 verifications: low risk and high risk.
- 1 journey with Day 7/30/90 check-ins.
- 1 overdue check-in.
- 1 complaint with evidence and a case note.
- 1 in-app notification per type.
- Device tokens/preferences are seeded in `notification-service`, not here.

---

## 6. Public API

### Conventions

- Base path: `/api/v1`
- Auth: `Authorization: Bearer <supabase_access_token>`
- Roles: `worker`, `caseworker`, `admin`
- JSON envelope:

```json
{
  "data": {},
  "meta": { "request_id": "..." }
}
```

- List meta adds `page`, `page_size`, `total`.
- Errors: `{"error": {"code": "...", "message": "...", "details": null}, "meta": {...}}`
- Pagination: `page` (1), `page_size` (20, max 100), `sort`, `order`.
- `Idempotency-Key` required on uploads, verification creation, check-in responses, complaint creation.
- Dates in ISO 8601 UTC.

### Endpoint inventory

#### Auth

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | Worker self-registration only |
| POST | `/auth/login` | public | Email/password staff login |
| POST | `/auth/otp/request` | public | Worker phone OTP |
| POST | `/auth/otp/verify` | public | Verify OTP, return session |
| POST | `/auth/refresh` | public | Refresh session |
| POST | `/auth/logout` | authenticated | Revoke session |
| GET | `/auth/me` | authenticated | Current profile |
| PATCH | `/auth/me` | authenticated | Name, language, country, phone |

#### Users and consents

| Method | Path | Role |
|---|---|---|
| GET | `/users` | staff |
| GET | `/users/{id}` | staff or self |
| PATCH | `/users/{id}` | staff or self |
| PATCH | `/users/{id}/role` | admin |
| PATCH | `/users/{id}/status` | admin |
| GET | `/users/me/consents` | worker |
| POST | `/users/me/consents` | worker |

#### Agencies

| Method | Path | Role |
|---|---|---|
| GET | `/agencies` | authenticated (`q`, status, district) |
| GET | `/agencies/{id}` | authenticated |
| GET | `/agencies/{id}/licenses` | authenticated |
| POST | `/agencies` | admin |
| PATCH | `/agencies/{id}` | admin |
| POST | `/agencies/import` | admin |
| GET | `/agencies/snapshots` | admin |

#### Verification

| Method | Path | Role |
|---|---|---|
| POST | `/verification` | worker (`Idempotency-Key`) |
| GET | `/verification` | worker own / staff all |
| GET | `/verification/{id}` | owner / staff |
| POST | `/verification/{id}/retry` | owner / admin |
| PATCH | `/verification/{id}/review` | staff |

#### Documents

| Method | Path | Role |
|---|---|---|
| POST | `/documents` | worker (`Idempotency-Key`) |
| GET | `/documents` | owner / staff |
| GET | `/documents/{id}` | owner / staff |
| GET | `/documents/{id}/download-url` | owner / staff (audited) |
| DELETE | `/documents/{id}` | owner / admin (soft delete) |
| POST | `/documents/{id}/reprocess` | staff |

#### Migration and check-ins

| Method | Path | Role |
|---|---|---|
| GET | `/migration/journeys` | worker own / staff all |
| POST | `/migration/journeys` | worker |
| GET | `/migration/journeys/{id}` | owner / staff |
| PATCH | `/migration/journeys/{id}` | owner / staff |
| POST | `/migration/journeys/{id}/consent` | worker |
| PATCH | `/migration/journeys/{id}/stage` | staff |
| GET | `/checkins` | worker own / staff all |
| GET | `/checkins/{id}` | owner / staff |
| POST | `/checkins/{id}/respond` | owner (`Idempotency-Key`) |
| GET | `/checkins/overdue` | staff |
| POST | `/checkins` | staff |
| PATCH | `/checkins/{id}` | staff |
| POST | `/checkins/{id}/escalate` | staff |

#### Complaints

| Method | Path | Role |
|---|---|---|
| POST | `/complaints` | worker (`Idempotency-Key`) |
| GET | `/complaints` | worker own / staff all |
| GET | `/complaints/{id}` | owner / staff |
| PATCH | `/complaints/{id}` | owner (draft only) / staff |
| POST | `/complaints/{id}/submit` | owner |
| POST | `/complaints/{id}/documents` | owner |

#### Notifications

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/notifications` | authenticated | In-app feed |
| GET | `/notifications/unread-count` | authenticated | |
| PATCH | `/notifications/{id}/read` | owner | |
| POST | `/notifications/read-all` | owner | |
| POST | `/notifications/devices` | authenticated | Proxied to `notification-service` |
| DELETE | `/notifications/devices/{token}` | owner | Proxied |
| GET | `/notifications/preferences` | authenticated | Proxied |
| PATCH | `/notifications/preferences` | authenticated | Proxied |

#### Chat and speech (proxied to `ai-service`)

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/chat/sessions` | worker | Create session via AI-service |
| GET | `/chat/sessions` | worker | List own sessions |
| GET | `/chat/sessions/{id}` | owner | Session metadata |
| POST | `/chat/sessions/{id}/messages` | owner | SSE stream |
| POST | `/chat/transcribe` | worker | Speech-to-text proxy |
| POST | `/chat/synthesize` | worker | Text-to-speech proxy |

#### Webhooks

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/webhooks/whatsapp` | provider | Verify Meta signature; forward to AI-service; idempotent by provider message ID |

#### Admin

| Method | Path | Role |
|---|---|---|
| GET | `/admin/dashboard` | staff |
| GET | `/admin/cases` | staff |
| GET | `/admin/cases/{id}` | staff |
| PATCH | `/admin/cases/{id}` | staff |
| GET | `/admin/cases/{id}/notes` | staff |
| POST | `/admin/cases/{id}/notes` | staff |
| POST | `/admin/cases/{id}/escalate` | staff |
| GET | `/admin/verifications/{id}/trace` | staff (proxies AI-service) |
| GET | `/admin/audit-logs` | admin |

#### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | DB, Redis, storage, internal clients |

### Internal endpoints exposed by core-api

| Method | Path | Consumer | Notes |
|---|---|---|---|
| GET | `/internal/v1/documents/{id}/content` | `ai-service` | Service JWT; returns bytes or short-lived signed URL |
| GET | `/internal/v1/agencies/{id}/license-history` | `ai-service` | Service JWT; license history for analysis |
| GET | `/internal/v1/health` | infrastructure | Internal readiness |
| GET | `/internal/v1/verifications/{id}` | `ai-service` | Job context if needed outside the event |
| POST | `/internal/v1/audit-events` | internal services | Optional audit forwarding |

### Internal endpoints consumed by core-api

| Service | Method | Path | Purpose |
|---|---|---|---|
| `ai-service` | POST | `/internal/v1/chat/sessions` | Create chat session |
| `ai-service` | GET | `/internal/v1/chat/sessions/{id}` | Session metadata |
| `ai-service` | POST | `/internal/v1/chat/sessions/{id}/messages` | SSE chat stream |
| `ai-service` | POST | `/internal/v1/speech/transcribe` | STT |
| `ai-service` | POST | `/internal/v1/speech/synthesize` | TTS |
| `ai-service` | GET | `/internal/v1/analyses/{verification_id}` | AI trace/run summary |
| `ai-service` | POST | `/internal/v1/webhooks/whatsapp` | Forward verified inbound WhatsApp messages |
| `notification-service` | POST | `/internal/v1/devices` | Register device token |
| `notification-service` | DELETE | `/internal/v1/devices/{token}` | Unregister |
| `notification-service` | GET | `/internal/v1/preferences/{user_id}` | Read preferences |
| `notification-service` | PUT | `/internal/v1/preferences/{user_id}` | Update preferences |

### OpenAPI

- `GET /openapi.json` is the public contract.
- `scripts/export_openapi.py` writes `docs/api/openapi.json`.
- Generate `admin-frontend/src/types/api.generated.ts`.
- Document the equivalent command for Person 2's worker web.
- CI fails if the committed OpenAPI is stale.

---

## 7. Event contracts

### Envelope

Every event:

```json
{
  "event_id": "uuid",
  "event_type": "verification.requested",
  "version": 1,
  "occurred_at": "2026-01-01T10:00:00Z",
  "producer": "core-api",
  "trace_id": "uuid",
  "data": {}
}
```

### `verification.requested.v1`

Stream: `vm:ai:requests` · Producer: `core-api` · Consumer: `ai-service`

```json
{
  "event_id": "7f7d...",
  "event_type": "verification.requested",
  "version": 1,
  "occurred_at": "2026-01-01T10:00:00Z",
  "producer": "core-api",
  "trace_id": "a1b2...",
  "data": {
    "verification_id": "9e8d...",
    "user_id": "3c4b...",
    "locale": "si",
    "agency": {
      "id": "1a2b...",
      "registration_no": "SLBFE/1234",
      "name": "Example Agency",
      "license_no": "LIC-5678",
      "license_status": "active",
      "license_expires_on": "2027-03-31"
    },
    "job": {
      "title": "Domestic Worker",
      "employer_name": "Example Employer",
      "destination_country": "SA",
      "offered_salary": 45000,
      "currency": "LKR"
    },
    "documents": [
      {
        "document_id": "4d5e...",
        "type": "job_offer",
        "mime_type": "application/pdf",
        "page_count": 2
      }
    ]
  }
}
```

### `verification.completed.v1`

Stream: `vm:ai:results` · Producer: `ai-service` · Consumer: `core-api`

```json
{
  "event_id": "8a9b...",
  "event_type": "verification.completed",
  "version": 1,
  "occurred_at": "2026-01-01T10:02:00Z",
  "producer": "ai-service",
  "trace_id": "a1b2...",
  "data": {
    "verification_id": "9e8d...",
    "status": "suspicious",
    "risk_level": "high",
    "risk_score": 82,
    "findings": [
      { "code": "salary_deduction", "message": "Deduction exceeds 20%", "source": "contract.pdf#p2" }
    ],
    "evidence": [
      { "document_id": "4d5e...", "page": 2, "quote": "..." }
    ],
    "engine_version": "ai-service@1.0.0",
    "analysis_run_id": "b2c3..."
  }
}
```

### `verification.failed.v1`

Stream: `vm:ai:results` · Producer: `ai-service` · Consumer: `core-api`

```json
{
  "event_id": "9b1c...",
  "event_type": "verification.failed",
  "version": 1,
  "occurred_at": "2026-01-01T10:02:00Z",
  "producer": "ai-service",
  "trace_id": "a1b2...",
  "data": {
    "verification_id": "9e8d...",
    "error_code": "document_unreadable",
    "message": "The uploaded PDF could not be parsed",
    "retryable": false
  }
}
```

### `notification.requested.v1`

Stream: `vm:notifications:requests` · Producer: `core-api` · Consumer: `notification-service`

```json
{
  "event_id": "0c1d...",
  "event_type": "notification.requested",
  "version": 1,
  "occurred_at": "2026-01-01T10:03:00Z",
  "producer": "core-api",
  "trace_id": "a1b2...",
  "data": {
    "notification_id": "1d2e...",
    "user_id": "3c4b...",
    "locale": "si",
    "type": "verification_complete",
    "title": "Verification complete",
    "body": "Your job offer has a high-risk finding. Tap to review.",
    "data": { "verification_id": "9e8d..." },
    "deep_link": "videshamitra://verifications/9e8d...",
    "channels": ["push", "whatsapp"]
  }
}
```

### `notification.delivery.updated.v1` (optional)

Stream: `vm:notifications:results` · Producer: `notification-service` · Consumer: `core-api`

Used only if the admin UI needs delivery status. Core ignores it until needed.

### Outbox and consumers

- Domain write + outbox insert in one transaction.
- Relay publishes pending rows with `FOR UPDATE SKIP LOCKED`.
- Mark `published` only after `XADD`.
- Retry with backoff; move exhausted rows to `failed` and log.
- Consumers create `event_dedupe` rows in the same transaction as side effects.
- Max attempts and dead-letter streams are mandatory.

---

## 8. Workstreams and tasks

Use `CORE-xx` in commits/PRs.

### WS0 — Service foundation

#### CORE-01 — Restructure repo to services

**Files:** root layout, `services/core-api/`, `packages/contracts/`

- Move `web-backend/` to `services/core-api/`.
- Add the `services/notification-service/` placeholder (yours); coordinate with Person 2 for the `services/ai-service/` scaffold.
- Add `packages/contracts/` with a README and versioning policy.
- Update imports, Dockerfiles, CI paths, and docs references.

**Done when:** `services/core-api` starts; no code remains in `web-backend/`.

#### CORE-02 — Core service configuration

**Files:** `services/core-api/pyproject.toml`, `.env.example`, `app/core/config.py`

- `SettingsConfigDict`; add all core env vars:
  `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWKS_URL`, `JWT_AUDIENCE`, `JWT_ISSUER`, `REDIS_URL`, `INTERNAL_JWT_SECRET`, `AI_SERVICE_URL`, `NOTIFICATION_SERVICE_URL`, `DOCUMENTS_BUCKET`, `MAX_UPLOAD_MB`, `SLBFE_SOURCE_URL`, `SLBFE_API_KEY`, `CORS_ORIGINS`, `LOG_LEVEL`, `ENVIRONMENT`.
- Add `asyncpg`, `redis[hiredis]`, `httpx`, `filetype`, `ruff`, `pytest-cov`.
- Add `Dockerfile` and `.dockerignore`.

**Done when:** service starts with a valid env and fails fast on missing required settings.

#### CORE-03 — Schemas, roles, migration runner

**Files:** `migrations/`, `app/db/migrate.py`, `supabase/bootstrap.sql`

- Create `core` schema and `core_api_role`.
- Grant only `core` to the role.
- Create `schema_migrations` and a runner that applies files in order inside transactions.
- Document local reset (`supabase start`, bootstrap, migrate).
- Ensure `ai`/`notification` roles are created by their owners; core must not access them.

**Done when:** `migrate` applies from empty and is idempotent.

#### CORE-04 — DB pool and health

**Files:** `app/db/pool.py`, `app/db/transaction.py`, `app/main.py`

- asyncpg pool on startup/shutdown.
- `get_connection()` dependency and transaction helper.
- `/health` liveness; `/ready` checks DB, Redis, storage, and internal clients.
- Request ID middleware.

**Done when:** readiness fails if Postgres/Redis/storage is unavailable.

#### CORE-05 — API conventions

**Files:** `app/api/errors.py`, `app/core/exceptions.py`, `app/core/request_id.py`, `app/core/idempotency.py`, `app/schemas/common.py`

- Envelope responses, error codes, pagination.
- Idempotency dependency backed by `idempotency_keys`.
- Validation/auth/not-found/conflict/internal handlers.
- `X-Request-ID` on every response.

**Done when:** duplicate mutating requests return the stored response; all errors use the envelope.

#### CORE-06 — OpenAPI and contracts package

**Files:** `app/main.py`, `scripts/export_openapi.py`, `packages/contracts/`, `docs/api/openapi.json`

- Add tags/examples/response models.
- Export OpenAPI.
- Add event JSON Schemas + Pydantic models to `packages/contracts`.
- Generate admin TS types and document worker web generation.
- CI staleness check.

**Done when:** OpenAPI and event schemas are committed and validated.

#### CORE-07 — Redis, outbox, event relay

**Files:** `app/events/*`, `app/workers/outbox_relay.py`, `app/services/outbox_service.py`

- Redis async client with health check.
- Event envelope + publisher.
- Outbox insert helper.
- Relay loop with `FOR UPDATE SKIP LOCKED`, backoff, attempts, failure state.
- Stream names/consumer groups per architecture doc.

**Done when:** a test event is written in a transaction and appears on the stream exactly once after commit; rollback publishes nothing.

#### CORE-08 — Internal auth and service clients

**Files:** `app/core/internal_auth.py`, `app/integrations/ai_client.py`, `app/integrations/notification_client.py`

- Issue/verify internal JWTs (`iss`, `aud`, `sub`, `exp` ≤ 5 min).
- Dependency for internal routes.
- Typed httpx clients with timeouts/retries and correlation headers.
- No service role keys in logs.

**Done when:** internal routes reject public tokens; internal clients reject wrong audience.

### WS1 — Auth, users, audit

#### CORE-09 — Supabase JWT and roles

**Files:** `app/core/security.py`, `app/api/dependencies.py`, `app/core/permissions.py`

- Verify JWKS (cache) or HS256 fallback.
- Validate signature, expiry, issuer, audience.
- Load `core.users`; reject inactive.
- `require_roles(...)`.
- Remove hardcoded demo user.

**Done when:** 401/403 matrix passes.

#### CORE-10 — Auth endpoints

**Files:** `app/api/v1/auth.py`, `app/services/auth_service.py`, `app/schemas/auth.py`

- Register/login/OTP/refresh/logout/me.
- Thin proxy over Supabase Auth via `httpx`.
- Self-registration always worker.
- Rate-limit OTP by IP/phone.
- Document SMS provider + dev fallback.

**Done when:** worker OTP and staff email login work end to end.

#### CORE-11 — Profiles and consents

**Files:** `app/api/v1/users.py`, `app/services/user_service.py`, `app/repositories/user_repository.py`, `app/schemas/user.py`

- Self profile update.
- Staff user list/detail.
- Admin role/status changes with audit.
- Consent grant/revoke.

**Done when:** only admins change roles; consent history is queryable.

#### CORE-12 — Audit service

**Files:** `app/services/audit_service.py`, `app/api/v1/admin.py` (read endpoint later)

- `record(actor, action, entity, metadata, request)`.
- Call from auth, documents, verification, cases, agencies, users.
- Admin query with filters.

**Done when:** sensitive actions appear with actor/entity and no PII leakage.

### WS2 — Agencies and SLBFE

#### CORE-13 — Agency repository and search

**Files:** `app/repositories/agency_repository.py`, `app/services/agency_service.py`, `app/models/agency.py`, `app/schemas/agency.py`

- Trigram search with `similarity()`.
- Detail + license history.
- Admin create/update.
- `get_license_changes(since)` and `list_workers_for_agency(agency_id)` for the watchdog.

**Done when:** fuzzy search handles spelling variants; unit tests cover normalization.

#### CORE-14 — Agency API

**Files:** `app/api/v1/agencies.py`

- Read for authenticated; write for admin.
- Import trigger endpoint.
- Audit writes.

**Done when:** unauthorized writes return 403; OpenAPI matches.

#### CORE-15 — SLBFE client, parser, import

**Files:** `app/integrations/slbfe/*`, `scripts/import_agencies.py`

- Fetch with timeout/retries/checksum.
- CSV/JSON first; PDF only if required.
- Normalize names/licenses/dates/statuses.
- Upsert agencies, insert license history, skip duplicate snapshots.
- CLI flags and dry-run.

**Done when:** same snapshot twice is a no-op; changed license creates history.

#### CORE-16 — Agency license watchdog

**Files:** `app/workers/agency_monitor.py`, `app/services/agency_service.py`

- Periodically compare latest license history to previous.
- Create in-app notifications for affected workers.
- Emit `notification.requested.v1`.
- Deduplicate alerts per agency/license change.

**Done when:** a suspended license generates one notification per affected worker.

### WS3 — Documents and verification

#### CORE-17 — Document storage

**Files:** `app/services/document_service.py`, `app/repositories/document_repository.py`, `app/schemas/document.py`

- Upload to private Supabase Storage.
- Validate type/size/pages; compute SHA-256; reject duplicates.
- Soft delete; signed URL generation.
- `get_bytes(document_id)` for the internal AI endpoint.
- Audit view/download.

**Done when:** upload/download/delete and duplicate rejection work.

#### CORE-18 — Document API and validation

**Files:** `app/api/v1/documents.py`, `app/utils/file_processing.py`

- Multipart upload with `Idempotency-Key`.
- Allowed MIME/extension/size limits.
- Staff reprocess endpoint.
- Document limits in API docs.

**Done when:** oversized/spoofed/empty files return 422; valid PDF/JPEG/PNG pass.

#### CORE-19 — Verification domain and state machine

**Files:** `app/repositories/verification_repository.py`, `app/services/verification_service.py`, `app/schemas/verification.py`

- Create/get/list/update.
- Resolve agency by fuzzy match when absent.
- State machine: `pending → processing → verified|suspicious|fraudulent|failed`.
- Persist findings/evidence/engine version/analysis_run_id.
- Retry and stale-processing recovery.
- Publish `verification.requested.v1` in the same transaction.

**Done when:** creating a verification writes the record + outbox event atomically.

#### CORE-20 — Verification API

**Files:** `app/api/v1/verification.py`

- Worker create/list/get; staff list/get/review.
- Return `202` while processing.
- Retry endpoint.
- Manual review with audit.

**Done when:** ownership is enforced; retry is idempotent; status polling works.

#### CORE-21 — AI result consumer

**Files:** `app/workers/ai_result_consumer.py`, `app/services/verification_service.py`

- Consume `vm:ai:results` with consumer group `core-api`.
- Dedupe by `event_id`.
- Apply completed/failed results idempotently.
- Create in-app notification + notification request.
- Handle unknown verification IDs and stale events.

**Done when:** duplicate result events do not change the final state twice.

#### CORE-22 — Internal service endpoints

**Files:** `app/api/internal/documents.py`, `app/api/internal/agencies.py`

- Service-JWT protected.
- Return bytes or a short-lived signed URL.
- Add the agency license-history endpoint for AI analysis.
- Audit AI access (no document content in logs).
- Enforce size/time limits.

**Done when:** AI-service can fetch a document; public tokens are rejected.

#### CORE-23 — Admin verification review

**Files:** `app/api/v1/admin.py`, `app/services/admin_service.py`

- List/filter verifications.
- Manual verdict with note and audit.
- Fetch AI trace via internal client (`/admin/verifications/{id}/trace`).

**Done when:** caseworkers can review and correct a result; trace is visible.

### WS4 — Journeys and check-ins

#### CORE-24 — Journey API

**Files:** `app/repositories/migration_repository.py`, `app/services/migration_service.py`, `app/api/v1/migration.py`

- Create/list/get/update journey.
- One active journey per user.
- Set `next_checkin_at`.
- Consent endpoint.
- Staff stage transitions.

**Done when:** worker sees the next check-in; staff can advance stage.

#### CORE-25 — Check-in API

**Files:** `app/api/v1/checkins.py`, `app/services/migration_service.py`

- List/get/respond/schedule/reschedule/cancel/escalate.
- Structured response + risk level.
- Idempotent respond.
- On high risk: create/escalate complaint.

**Done when:** a due check-in can be answered once; high-risk response creates a case.

#### CORE-26 — Check-in scheduler worker

**Files:** `app/workers/checkin_worker.py`

- Schedule Day 7/30/90 on consent.
- Find due check-ins with `FOR UPDATE SKIP LOCKED`.
- Mark sent, create in-app notification, emit `notification.requested.v1`.
- Mark missed after grace period.

**Done when:** due check-ins are sent once; restarts do not duplicate.

#### CORE-27 — Missed check-in escalation

**Files:** `app/workers/checkin_worker.py`, `app/services/migration_service.py`

- After grace period, mark `missed`.
- Create/escalate a tier-2 case.
- Notify staff and worker.
- Audit.

**Done when:** missed check-ins appear in the overdue admin list exactly once.

### WS5 — Notifications feed and proxy

#### CORE-28 — In-app notification service/feed

**Files:** `app/services/notification_service.py`, `app/repositories/notification_repository.py`, `app/api/v1/notifications.py`

- Create/list/unread count/mark read/read all.
- Feed only; no delivery.
- Deep-link field stored.

**Done when:** feed and unread count are consistent under concurrent reads.

#### CORE-29 — Notification request publisher

**Files:** `app/services/notification_service.py`, `app/events/*`

- `request_delivery(...)` creates in-app notification + outbox event.
- Event includes user, locale, type, title, body, data, deep_link, channels.
- Respect core-side consent flags before requesting WhatsApp.

**Done when:** one method call creates the feed item and exactly one outbox event.

#### CORE-30 — Notification-service proxy

**Files:** `app/api/v1/notifications.py`, `app/integrations/notification_client.py`

- Device register/unregister and preferences read/update.
- Validate auth, pass `user_id` + payload with internal JWT.
- Do not store tokens or preferences in core.
- Handle notification-service 4xx/5xx consistently.

**Done when:** mobile/web can register a token through core; token is visible only in notification-service.

### WS6 — Complaints and admin

#### CORE-31 — Complaint API

**Files:** `app/services/complaint_service.py`, `app/repositories/complaint_repository.py`, `app/api/v1/complaints.py`, `app/schemas/complaint.py`

- Create draft, edit draft, submit, attach documents.
- Worker sees own; staff sees all.
- Evidence references document IDs.
- Idempotent create.

**Done when:** worker can file a complaint with evidence; staff can read it.

#### CORE-32 — Case management service

**Files:** `app/services/case_service.py`, `app/repositories/complaint_repository.py`

- List/filter cases.
- Detail with worker, agency, verification, documents, notes, AI trace reference.
- Update status/assignee/tier.
- Add note; escalate.
- Audit every staff action.

**Done when:** a caseworker can complete the seeded review flow through the API.

#### CORE-33 — Admin case API

**Files:** `app/api/v1/admin.py`

- Implement `/admin/cases` endpoints.
- Role guard: caseworker/admin.
- Pagination/filtering.
- Validation for status transitions.

**Done when:** case list/detail/notes/escalate work; invalid transitions return 409.

#### CORE-34 — Admin dashboard

**Files:** `app/api/v1/admin.py`, `app/services/admin_service.py`, `app/schemas/admin.py`

- Metrics: workers, active journeys, verifications/week, high-risk verifications, open cases by tier, overdue check-ins, agency alerts.
- Recent activity.
- Optimized queries + indexes.

**Done when:** dashboard responds in <500ms on seeded data.

#### CORE-35 — Admin users and audit

**Files:** `app/api/v1/admin.py`, `app/api/v1/users.py`

- User list/detail/role/status.
- Audit log list/filters.
- Admin-only guards.

**Done when:** role change appears in audit; caseworker cannot read audit logs.

### WS7 — Chat and speech integration

#### CORE-36 — Chat proxy

**Files:** `app/api/v1/chat.py`, `app/integrations/ai_client.py`

- Create/list/get sessions via AI-service.
- Stream SSE messages from AI-service to the client.
- Propagate request/trace IDs.
- Handle AI-service timeouts and disconnects.
- Do not persist chat content in core.
- Verify WhatsApp webhook signatures and forward inbound messages to AI-service with provider-message idempotency.

**Done when:** worker web/mobile can stream a chat response through core; AI-service is not public.

#### CORE-37 — Speech proxy

**Files:** `app/api/v1/chat.py`, `app/integrations/ai_client.py`

- Transcribe and synthesize endpoints.
- Enforce audio size/type/duration limits.
- Stream or return audio safely.
- Audit? Optional for speech.

**Done when:** voice input/output works through core without exposing AI-service.

#### CORE-38 — Admin AI trace proxy

**Files:** `app/api/v1/admin.py`, `app/integrations/ai_client.py`

- `GET /admin/verifications/{id}/trace` → AI-service trace.
- Staff only.
- Redact internal prompts/secrets if needed.
- Audit access.

**Done when:** case detail can show agent trace without giving the browser an internal token.

### WS8 — Admin portal

#### CORE-39 — Admin bootstrap, auth, routing

**Files:** `admin-frontend/package.json`, `src/main.jsx`, `src/app/*`, `src/lib/*`

- Remove Vite scaffold mount/assets.
- Add Supabase, TanStack Query/Table, react-hook-form, zod, date-fns, recharts, clsx, tailwind-merge, sonner.
- Providers, error boundary, router, 403/404.
- Supabase session handling; fetch `/auth/me`; reject non-staff.
- API client with bearer token, 401 retry, error normalization.

**Done when:** staff login works; worker login is rejected.

#### CORE-40 — Admin design system and layout

**Files:** `src/components/ui/*`, `src/components/layout/*`

- Buttons, inputs, select, textarea, modal, confirm dialog.
- DataTable, pagination, badges, spinner, skeleton, empty/error states, toast.
- AdminLayout, Sidebar, Header, Breadcrumbs.
- Accessible focus/ARIA.

**Done when:** all pages use the shared components.

#### CORE-41 — Admin dashboard page

**Files:** `src/features/dashboard/pages/AdminDashboardPage.tsx`

- Metric cards, risk chart, verification trend, recent cases, overdue check-ins, agency alerts.
- Loading/empty/error states.

**Done when:** live dashboard renders seeded metrics.

#### CORE-42 — Admin cases pages

**Files:** `src/features/case-management/pages/*`, feature components

- Case queue: search, status/tier/assignee filters, pagination.
- Case detail: overview, evidence, documents, AI trace, notes.
- Actions: assign, status, note, escalate.
- Confirmation and optimistic updates.

**Done when:** caseworker completes the seeded flow in the UI.

#### CORE-43 — Agencies, users, audit pages

**Files:** `src/features/agencies/`, `src/features/users/`, `src/features/audit/`

- Agencies: search, license status, detail, import (admin).
- Users: list/role/status (admin).
- Audit: filters + detail.
- Role guards.

**Done when:** caseworkers see read-only agency/case data; admins manage users/audit.

#### CORE-44 — Admin tests

**Files:** `vitest.config.ts`, `playwright.config.ts`, `e2e/`

- Component tests for tables, forms, guards.
- E2E: login, dashboard, case queue, case detail, note, escalate, audit.
- Seed fixture.

**Done when:** `npm run test` and `npm run test:e2e` pass in CI.

### WS9 — Ops and quality

#### CORE-45 — CI

**Files:** `.github/workflows/ci.yml`

- Per-service jobs; core lint/typecheck/test/build.
- Use the Supabase CLI local stack for `auth`/`storage` fidelity, or a CI bootstrap that creates minimal `auth`/`storage` stubs; run core migrations against it. Add a Redis service.
- Contract tests for events.
- Admin lint/build/unit/E2E.
- Docker build.
- No `|| echo "No tests yet"`.

**Done when:** failures block merges.

#### CORE-46 — Docker Compose and Kong

**Files:** `docker-compose.yml`, `infra/kong/kong.yml`, Dockerfiles

- Services: `core-api`, `core-api-worker`, `ai-service`, `notification-service`, `redis`, `kong`.
- Internal network for services; only Kong published.
- Healthchecks and `depends_on` conditions.
- Kong routes only `/api/v1` and `/health` to core-api.
- Request size limits and rate limits.

**Done when:** `docker compose up --build` brings up healthy services.

#### CORE-47 — Observability

**Files:** `app/core/logging.py`, `app/core/request_id.py`, `app/events/*`

- JSON logs with service/route/status/latency/user ID (not PII).
- Propagate `X-Request-ID`/`trace_id` in HTTP and events.
- `/health`, `/ready`, optional `/metrics`.
- Dead-letter visibility.

**Done when:** one verification can be traced across core → AI → core via IDs.

#### CORE-48 — Documentation and cleanup

**Files:** `README.md`, `docs/architecture/*`, `docs/api/*`, `docs/database/*`, `docs/work-division.md`

- Update setup for the 3-service architecture.
- Document public vs internal APIs, events, data ownership.
- Update schema docs with `core`/`ai`/`notification` schemas.
- Delete `repo-to-text_1795342648.txt` and scaffold leftovers.
- Link plans from README.

**Done when:** a new developer can run core + stubs and understand the boundaries.

#### CORE-49 — Contract and integration tests

**Files:** `tests/contracts/`, `tests/integration/`, `tests/e2e/`

- Event schema validation.
- Outbox → stream → consumer round trip.
- AI result duplicate/ordering tests.
- Notification request tests.
- E2E with AI/notification stubs.

**Done when:** the full verification flow passes with stubs.

#### CORE-50 — Release smoke test

- Fresh Supabase + Redis + core + AI stub + notification stub + admin.
- Worker creates verification; AI stub returns high risk; case appears; caseworker escalates.
- Notification request appears in the stream; stub delivery succeeds.
- Audit log records the flow.
- Docker Compose healthy.

**Done when:** the end-to-end demo works from a clean environment.

---

## 9. Handoffs

### Core-api provides

1. `core` migrations + roles + seed.
2. Public OpenAPI + generated TS types.
3. Event schemas + outbox/publisher.
4. Internal JWT verification and service clients.
5. Document content internal endpoint.
6. Public notification feed + device/preference proxies.
7. Public chat/speech proxies.
8. Admin APIs for cases/traces.
9. Error/pagination/idempotency conventions.

### Core-api receives

1. `verification.completed.v1` / `verification.failed.v1` from AI-service.
2. AI internal endpoints for chat/speech/traces.
3. Notification-service internal device/preference APIs.
4. Optional delivery updates.

### Frozen contracts

- Event envelope + 4 event types.
- Public API response/error/pagination.
- Internal JWT claims.
- Verification result schema.
- Notification request payload.
- Chat SSE event names.
- Device/preference request/response shapes.

### Interface sketches

```python
class VerificationService(Protocol):
    async def create(self, user: CurrentUser, payload: VerificationCreate) -> Verification: ...
    async def handle_result(self, event: VerificationResultEvent) -> None: ...

class NotificationPublisher(Protocol):
    async def request_delivery(
        self, user_id: UUID, type: str, title: str, body: str,
        data: dict, deep_link: str, channels: list[str],
    ) -> Notification: ...

class DocumentStorage(Protocol):
    async def get_bytes(self, document_id: UUID) -> bytes: ...
    async def get_signed_url(self, document_id: UUID, expires_in: int) -> str: ...
```

---

## 10. Milestones

### M0 — Service foundation

CORE-01 → CORE-08

**Exit:** core service runs, migrations apply, events publish, internal auth works, OpenAPI exported.

### M1 — Identity and agencies

CORE-09 → CORE-16

**Exit:** worker OTP/staff login, agency search/import, license watchdog.

### M2 — Documents and verification orchestration

CORE-17 → CORE-23

**Exit:** upload → verification → AI event → result consumer → status polling works with an AI stub.

### M3 — Journeys and check-ins

CORE-24 → CORE-27

**Exit:** Day 7/30/90 scheduling, responses, missed escalation.

### M4 — Notifications and complaints

CORE-28 → CORE-33

**Exit:** in-app feed, notification requests, device proxy, complaint/case APIs.

### M5 — Admin

CORE-34 → CORE-44

**Exit:** dashboard, case review, notes/escalation, audit, admin portal E2E.

### M6 — Chat/speech integration

CORE-36 → CORE-38

**Exit:** worker web/mobile chats through core; admin sees trace.

### M7 — Hardening

CORE-45 → CORE-50

**Exit:** CI, Compose, docs, contract tests, smoke test.

---

## 11. Testing

- **Unit:** JWT/roles, search, state machines, idempotency, outbox, notification publishing, file validation.
- **API:** 401/403 matrix, ownership, pagination, upload limits, idempotent check-ins/complaints.
- **Events:** schema validation, outbox atomicity, duplicate results, consumer dedupe, dead-letter.
- **Contract:** OpenAPI snapshot, event schema compatibility, internal client stubs.
- **Integration:** Postgres + Redis + core + AI stub + notification stub.
- **E2E:** worker creates verification → high-risk result → admin case review → escalation.
- **RLS:** worker cannot read another worker's rows; staff can.
- **Migrations:** empty database (with Supabase `auth`/`storage` or CI stubs) → all core migrations.

Fixtures:

- `worker_low_risk`, `worker_high_risk`, `caseworker`, `admin`.
- Agencies: active, suspended, expired, mismatch.
- Documents: text PDF, scanned image, oversized, spoofed MIME.
- Verification result events: completed, failed, duplicate, stale.

---

## 12. Deployment and operations

### Environment

```text
ENVIRONMENT=development
DATABASE_URL=postgresql://core_api_role:...@localhost:54322/postgres
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
SUPABASE_JWKS_URL=...
JWT_AUDIENCE=authenticated
JWT_ISSUER=...
REDIS_URL=redis://localhost:6379/0
INTERNAL_JWT_SECRET=...
AI_SERVICE_URL=http://ai-service:8010
NOTIFICATION_SERVICE_URL=http://notification-service:8020
DOCUMENTS_BUCKET=documents
MAX_UPLOAD_MB=25
SLBFE_SOURCE_URL=...
SLBFE_API_KEY=...
CORS_ORIGINS=["http://localhost:5173","http://localhost:5174"]
LOG_LEVEL=INFO
```

### Processes

- `core-api`: HTTP server.
- `core-api-worker`: outbox relay, AI result consumer, check-in scheduler, agency monitor, idempotency cleanup.

Both use the same image and code; different commands. This is not a separate microservice.

### Compose services

`kong`, `core-api`, `core-api-worker`, `ai-service`, `notification-service`, `redis`, plus local Supabase via CLI.

### Release checklist

- [ ] `services/core-api` migrations apply from empty.
- [ ] `core` schema/role isolation verified.
- [ ] Auth 401/403 matrix passes.
- [ ] OpenAPI exported and generated types compile.
- [ ] Outbox/stream round trip passes.
- [ ] AI stub result updates verification exactly once.
- [ ] Notification request reaches notification stub.
- [ ] Check-in scheduler and missed escalation work.
- [ ] Admin case flow and audit work.
- [ ] `docker compose up --build` healthy.
- [ ] No cross-schema queries.
- [ ] No secrets in clients/logs.
- [ ] `repo-to-text_1795342648.txt` removed.

---

## 13. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Event loss/duplicates | Wrong verification/notification state | Outbox, at-least-once, dedupe, replay tooling |
| AI-service unavailable | Verifications stuck | Queue persistence, retry, stale-processing recovery |
| Notification-service unavailable | Missed reminders | Stream retention, retries, dead-letter monitoring |
| Shared Postgres temptation | Distributed monolith | Separate roles/schemas, no cross-schema grants, code review |
| Internal auth bypass | Data exposure | Network isolation, audience checks, tests |
| Chat proxy complexity | Broken streaming | SSE heartbeat, timeouts, disconnect handling, buffer limits |
| Large uploads | Cost/latency | Client compression, size limits, signed URLs |
| Event schema drift | Consumer failures | Versioned contracts + compatibility CI |
| Admin scope creep | Delayed case flow | Ship case queue/detail/note/escalate first |

---

## 14. File checklist

### Create

```
services/core-api/app/api/internal/documents.py
services/core-api/app/api/internal/agencies.py
services/core-api/app/api/internal/health.py
services/core-api/app/api/v1/chat.py
services/core-api/app/api/v1/complaints.py
services/core-api/app/events/envelope.py
services/core-api/app/events/publisher.py
services/core-api/app/events/consumer.py
services/core-api/app/events/schemas.py
services/core-api/app/workers/outbox_relay.py
services/core-api/app/workers/ai_result_consumer.py
services/core-api/app/workers/checkin_worker.py
services/core-api/app/workers/agency_monitor.py
services/core-api/app/integrations/ai_client.py
services/core-api/app/integrations/notification_client.py
services/core-api/app/integrations/supabase/storage.py
services/core-api/app/services/case_service.py
services/core-api/app/repositories/notification_repository.py
services/core-api/migrations/001_core_foundation.sql ... 010_indexes.sql
services/core-api/tests/conftest.py
services/core-api/tests/factories.py
services/core-api/tests/fakes/
packages/contracts/
docs/core-api-plan.md
docs/architecture/microservices.md
```

### Replace

```
services/core-api/pyproject.toml
services/core-api/app/core/*.py
services/core-api/app/api/dependencies.py
services/core-api/app/api/router.py
services/core-api/app/models/*.py
services/core-api/app/repositories/*.py
services/core-api/app/services/*.py
services/core-api/app/schemas/*.py
services/core-api/app/api/v1/{auth,users,agencies,verification,documents,migration,checkins,notifications,admin}.py
services/core-api/app/main.py
services/core-api/scripts/import_agencies.py
admin-frontend/src/main.jsx
admin-frontend/src/app/*
admin-frontend/src/lib/*
admin-frontend/src/components/**
admin-frontend/src/features/**
admin-frontend/package.json
admin-frontend/index.html
docker-compose.yml
infra/kong/kong.yml
.github/workflows/ci.yml
README.md
docs/architecture/overview.md
docs/api/endpoints.md
docs/database/schema.md
docs/work-division.md
```

### Delete

```
web-backend/                          # after moving to services/core-api
repo-to-text_1795342648.txt
admin-frontend/src/App.jsx
admin-frontend/src/App.css
admin-frontend/src/assets/hero.png
admin-frontend/src/assets/react.svg
admin-frontend/src/assets/vite.svg
```

---

## 15. Start order

1. Move `web-backend` to `services/core-api`; add contracts package.
2. Create `core` schema/role and migration runner.
3. Add config, DB pool, health/ready, API conventions.
4. Add Redis, outbox, event envelope, relay.
5. Implement JWT auth and `/auth/me`.
6. Export OpenAPI; publish contracts to Person 2.
7. Implement agencies + SLBFE import.
8. Implement document storage + verification orchestration + AI result consumer.
9. Implement journeys + check-in scheduler.
10. Implement in-app notifications + notification requests + device proxy.
11. Implement complaints + admin case APIs.
12. Build admin portal auth/shell/case queue/case detail.
13. Add chat/speech proxies.
14. Add CI, Compose, observability, contract tests.
15. Run the release smoke test with AI/notification stubs.
