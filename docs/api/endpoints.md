# API Endpoints Specification

Prefix: `/api/v1`

> **Only `core-api` is public.** Kong routes public traffic to `core-api`. `ai-service` and `notification-service` expose internal APIs that are not reachable from clients.

## Service ownership

| API | Service | Notes |
|---|---|---|
| Public `/api/v1/*` | `core-api` | Auth, users, agencies, verification, documents, journeys, check-ins, complaints, notifications feed, admin |
| `/api/v1/chat/*` | `core-api` proxy | Authenticates and proxies SSE to `ai-service` |
| `/api/v1/notifications/devices` + `/preferences` | `core-api` proxy | Forwards to `notification-service` with a service JWT |
| Internal `/internal/v1/*` | `ai-service` | Chat sessions/SSE, speech, AI traces — core-api only |
| Internal `/internal/v1/*` | `notification-service` | Device tokens, preferences — core-api only |
| Internal `/internal/v1/documents/*` | `core-api` | Document content for `ai-service` |

## Public modules

- `/auth`: registration, login, token refresh, phone OTP for mobile onboarding
- `/users`: profiles, consents, staff user management
- `/agencies`: SLBFE agency search, license history, admin import
- `/verification`: job offer and recruitment agency verification; async AI orchestration
- `/documents`: multi-page uploads from web or mobile camera; signed downloads
- `/migration`: worker journey stages and stage transitions
- `/checkins`: scheduled safety check-ins and responses
- `/complaints`: complaint filing, evidence, caseworker review inputs
- `/notifications`: in-app feed, unread count, preferences/device proxies
- `/chat`: AI chat and speech proxies
- `/admin`: dashboard, case review, notes, escalation, audit logs
- `/webhooks`: WhatsApp and provider callbacks (routed to core-api)

## Internal APIs

### `ai-service` (called by `core-api`)

- `POST /internal/v1/chat/sessions`
- `GET /internal/v1/chat/sessions?user_id=`
- `GET /internal/v1/chat/sessions/{id}`
- `POST /internal/v1/chat/sessions/{id}/messages` (SSE)
- `POST /internal/v1/speech/transcribe`
- `POST /internal/v1/speech/synthesize`
- `GET /internal/v1/analyses/{verification_id}`
- `POST /internal/v1/webhooks/whatsapp`

### `notification-service` (called by `core-api`)

- `POST /internal/v1/devices`
- `DELETE /internal/v1/devices/{token}`
- `GET /internal/v1/preferences/{user_id}`
- `PUT /internal/v1/preferences/{user_id}`

### `core-api` (called by `ai-service` / infrastructure)

- `GET /internal/v1/documents/{id}/content` — raw bytes (audited; `ai-service` tokens only)
- `GET /internal/v1/agencies/{id}/license-history` — `ai-service` tokens only
- `GET /internal/v1/verifications/{id}` — job context outside the event; `ai-service` tokens only
- `POST /internal/v1/audit-events` — optional audit forwarding
- `GET /internal/v1/health`

All internal calls require a short-lived service JWT (HS256, `iat` and `exp`
required, lifetime ≤ 300 s) with the correct audience. Public Supabase tokens are
rejected on these routes. The full ai-service contract is in
[`docs/ai-agents/multi-agent-spec.md`](../ai-agents/multi-agent-spec.md).

`ai-service` must also serve `GET /internal/v1/health`; core's `/ready` probes it.

## Event contracts

Asynchronous flows use versioned events on Redis Streams:

- `verification.requested.v1` — `core-api` → `ai-service`
- `verification.completed.v1` / `verification.failed.v1` — `ai-service` → `core-api`
- `notification.requested.v1` — `core-api` → `notification-service`
- `notification.delivery.updated.v1` — `notification-service` → `core-api` (optional)

See [`docs/architecture/microservices.md`](../architecture/microservices.md) for payloads and stream names.

## Contract status

`services/core-api` implements the public modules above, with response/error
envelopes, pagination, request IDs, idempotency, and the event contracts in
[`packages/contracts`](../../packages/contracts/). The generated contract is
[`openapi.json`](openapi.json).

`ai-service` and `notification-service` internal contracts are frozen and
implemented; `notification-service` live FCM/WhatsApp delivery is pending
provider credentials.

## Mobile client contract

- `POST /notifications/devices` — register an FCM push token; `DELETE /notifications/devices/{token}` unregisters it on logout; `core-api` proxies both to `notification-service`
- `POST /chat/sessions/{id}/messages` — send a message and receive an SSE stream proxied through `core-api`; `attachments` are document UUIDs owned by the caller
- `POST /documents` — multipart upload from camera/document picker, with size and MIME limits
- `Idempotency-Key` header — required on queued `POST` requests to `/checkins/{id}/respond`, `/complaints`, `/verification`, and `/documents`
