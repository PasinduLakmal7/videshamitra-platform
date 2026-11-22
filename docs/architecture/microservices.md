# VideshaMitra Microservice Architecture

> **Deep dive:** the whole-platform view (context, flows, data, security,
> deployment, reliability) is in [`system-architecture.md`](system-architecture.md).
>
> **Status:** `core-api` is implemented (M0–M4 backend, admin APIs, chat/speech
> proxies, CI/Compose/contracts). `ai-service` and `notification-service` remain
> separate deployables; the notification service is a documented placeholder.
> See [`docs/progress.md`](../progress.md).

## 1. Goals

- Keep **one public API** so web and mobile clients do not deal with service routing.
- Give the **AI workload** its own deployable unit: long-running OCR/LLM jobs, LangGraph checkpoints, chat streaming, and speech.
- Give **notification delivery** its own deployable unit: device tokens, preferences, retries, and channel-specific failures.
- Keep the transactional core (identity, agencies, verification records, documents, journeys, check-ins, complaints, admin) in one service with one database.
- Keep the system operable by a two-person team.

## 2. Services

| Service | Responsibility | Public | Owner |
|---|---|---|---|
| `core-api` | Auth/users, agencies/SLBFE, verification orchestration, document metadata/storage, journeys, check-ins, complaints/cases, in-app notification feed, admin, audit, chat proxy | **Yes** (via Kong) | Person 1 |
| `ai-service` | LangGraph agents, OCR/document extraction, LLM calls, chat sessions/streaming, speech STT/TTS, AI traces, checkpoints | No | Person 2 |
| `notification-service` | Device tokens, notification preferences, Expo/FCM/WhatsApp delivery, retries, delivery status | No | Person 1 |
| Kong | Public gateway, routing, CORS, rate limits | Edge | Person 1 |
| Supabase | Postgres cluster, Auth, Storage | Infrastructure | Person 1 |
| Redis | Event streams / async jobs | Infrastructure | Person 1 |

Clients only ever call Kong → `core-api`. `ai-service` and `notification-service` are internal.

## 3. Data ownership

Each service owns its schema and credentials. There are **no cross-schema joins** and **no cross-service foreign keys**.

| Data | Owner | Notes |
|---|---|---|
| Users, roles, consents | `core-api` | Source of truth; Supabase Auth owns identity |
| Agencies, snapshots, license history | `core-api` | SLBFE imports |
| Verifications and evidence | `core-api` | Orchestration record + final result |
| Document metadata + blobs | `core-api` | Blobs in Supabase Storage; metadata in `core` schema |
| Journeys, check-ins | `core-api` | Scheduling and responses |
| Complaints/cases, case notes | `core-api` | Staff review and escalation |
| In-app notifications | `core-api` | Feed, unread count, read state |
| Audit logs | `core-api` | Sensitive action trail |
| Outbox/event delivery state | `core-api` | Each producer owns its outbox |
| AI runs, agent traces, OCR text | `ai-service` | `ai` schema; checkpoints and chat history |
| LangGraph checkpoints | `ai-service` | Owned by the agent runtime |
| Device tokens, preferences | `notification-service` | No copies in `core` |
| Delivery attempts/status | `notification-service` | Source of truth for delivery |
| Auth identities | Supabase Auth | Managed service |

**Rule:** services reference each other by ID only. A service never reads another service's tables, even on the same Postgres cluster.

### Local vs production

- **Local/dev:** one Postgres cluster with schemas `core`, `ai`, `notification`, one role per service.
- **Production:** separate databases (or at minimum separate clusters/credentials) per service. No shared superuser.
- **Migrations:** each service owns `services/<service>/migrations` and its own migration runner. Supabase CLI only runs the local stack and manages Auth/Storage.

## 4. Communication

### Synchronous internal REST

Used only for fast request/response or streaming interactions:

- `core-api → ai-service`: chat SSE, speech transcription/synthesis, AI trace lookup.
- `core-api → notification-service`: device registration, preferences.
- `ai-service → core-api`: fetch document content and agency license history for analysis.

All internal calls use a short-lived **internal JWT** and short timeouts. No public route exists for internal services.

### Asynchronous events

Used for long-running work and fan-out:

```
core-api ── verification.requested.v1 ──▶ Redis stream ──▶ ai-service
core-api ◀─ verification.completed.v1 ─── Redis stream ◀── ai-service
core-api ── notification.requested.v1 ──▶ Redis stream ──▶ notification-service
```

- **Outbox pattern:** the domain write and event insert happen in one database transaction. A relay publishes events and marks them sent.
- **At-least-once delivery:** every consumer deduplicates by `event_id`.
- **Retries:** bounded exponential backoff; exhausted events go to a dead-letter stream.
- **Schemas:** versioned JSON Schema/Pydantic models in `packages/contracts/`.

### Streams and consumer groups

| Stream | Producer | Consumer group | Payload |
|---|---|---|---|
| `vm:ai:requests` | `core-api` | `ai-service` | `verification.requested.v1` |
| `vm:ai:results` | `ai-service` | `core-api` | `verification.completed.v1`, `verification.failed.v1` |
| `vm:notifications:requests` | `core-api` | `notification-service` | `notification.requested.v1` |
| `vm:notifications:results` | `notification-service` | `core-api` | `notification.delivery.updated.v1` (optional) |

Event envelope:

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

## 5. Key flows

### Verification

1. Worker uploads documents to `core-api`.
2. Worker creates a verification in `core-api`.
3. `core-api` writes the verification + `verification.requested.v1` outbox event in one transaction.
4. Outbox relay publishes to `vm:ai:requests`.
5. `ai-service` consumes the event, fetches document bytes from `core-api`'s internal endpoint, runs OCR + LangGraph analysis, stores its traces/checkpoints, and publishes `verification.completed.v1` or `verification.failed.v1`.
6. `core-api` result consumer updates the verification, creates an in-app notification, and emits `notification.requested.v1`.
7. Client polls `GET /verification/{id}` or receives the in-app notification.

### Check-in

1. `core-api` schedules Day 7/30/90 check-ins when journey consent is granted.
2. A core worker finds due check-ins, marks them sent, creates an in-app notification, and emits `notification.requested.v1`.
3. Worker responds via `core-api`.
4. High-risk or missed responses create/escalate a complaint and notify staff.

### Notification

1. `core-api` writes an in-app notification and an outbox event.
2. `notification-service` consumes, loads preferences and device tokens, sends push/WhatsApp, and retries failures.
3. Delivery status stays in `notification-service`; `core-api` may expose an admin proxy if needed.

### Chat

1. Client calls `core-api /api/v1/chat`.
2. `core-api` authenticates, rate-limits, and proxies the SSE stream to `ai-service /internal/v1/chat/stream`.
3. `ai-service` owns chat sessions, LangGraph state, and traces.
4. `core-api` streams tokens back to the client.

## 6. Auth and security

- **Public auth:** Supabase JWT verified by `core-api`. Roles live in `core.users`.
- **Internal auth:** short-lived JWT signed with `INTERNAL_JWT_SECRET`, with `iss`, `aud`, `sub=service-name`, and `exp`. Every service verifies audience.
- **Network:** only Kong and `core-api` are on the edge network. `ai-service`, `notification-service`, Redis, and Postgres are on an internal network with no published ports.
- **Secrets:** service-specific env files; no service-role keys in clients or logs.
- **Rate limits:** Kong for public traffic; internal quotas for AI jobs.
- **PII:** AI-service receives only the document/user identifiers needed; logs redact document contents.

## 7. Deployment topology

Local:

```
Kong :8000
 └─ core-api :8001 (published internally)
     ├─ Supabase Postgres (core schema) + Auth + Storage
     ├─ Redis :6379
     ├─ ai-service :8010 (internal)
     └─ notification-service :8020 (internal)
```

Production:

- One container per service: `core-api`, `core-api-worker`, `ai-service`, `notification-service`, `notification-worker`.
- Managed Postgres + Redis, or separate Postgres instances per service.
- Kong remains the only public entry point.
- Per-service health checks, migrations, and CI.
- `core-api-worker` uses the same image as `core-api` with a different command.

## 8. Repository layout

Target monorepo layout:

```
videshamitra-platform/
├── services/
│   ├── core-api/
│   │   ├── app/
│   │   ├── migrations/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── ai-service/
│   └── notification-service/
├── packages/
│   └── contracts/              # event schemas, internal API models, generated types
├── admin-frontend/
├── web-frontend/
├── supabase/                   # local Supabase config + auth/storage bootstrap
├── infra/                      # Kong, Docker, deployment
├── docs/
├── docker-compose.yml
└── .github/
```

Migration from the original scaffold (completed):

1. Move `web-backend/` → `services/core-api/`.
2. Add `services/ai-service/` and `services/notification-service/` skeletons.
3. Add `packages/contracts/`.
4. Add Redis + outbox to Compose.
5. Add per-service migrations and roles.
6. Update Kong and CI.

## 9. Failure and consistency

- No distributed transactions. Use the outbox, idempotent consumers, and compensating actions.
- Verification state machine: `pending → processing → verified | suspicious | fraudulent | failed`.
- A stale `processing` verification is re-queued after a timeout; retries are bounded.
- If AI-service is down, verifications stay queued and the client sees `processing`; no data is lost.
- If notification-service is down, notification requests stay in the stream/outbox and are retried.
- Dead-letter streams are monitored; an operator can replay events.
- Event consumers store `event_id` in a dedupe table before applying side effects.

## 10. Observability

- Propagate `X-Request-ID` and `trace_id` across HTTP and events.
- Structured JSON logs with service name, route, status, latency, user ID (not PII), event ID, verification ID.
- `/health` (liveness) and `/ready` (DB/Redis/dependency) for every service.
- Metrics: request latency, error rate, queue lag, AI job duration, delivery failure rate.
- Optional Sentry/OpenTelemetry behind env flags.

## 11. Testing

- **Unit tests** inside each service.
- **Contract tests** for event schemas and internal APIs.
- **Consumer tests** with fake Redis streams.
- **Integration tests** with Compose: core + stubs for AI/notification.
- **E2E**: worker web/mobile → core → ai stub → result → notification stub.
- **Migration tests** from an empty database.
- No service test reaches into another service's database.

## 12. Decisions

| # | Decision | Choice |
|---|---|---|
| M1 | Public API owner | `core-api` only |
| M2 | AI execution | Async via Redis Streams, not synchronous request path |
| M3 | Notification execution | Async via Redis Streams; device/preferences via internal REST |
| M4 | Event delivery | Transactional outbox + at-least-once + dedupe |
| M5 | Internal auth | Short-lived service JWT |
| M6 | Databases | Separate schemas locally, separate databases recommended in production |
| M7 | Service discovery | Docker Compose/Kong locally; managed DNS/network in production |
| M8 | Chat | `core-api` authenticates and proxies SSE to `ai-service` |
| M9 | Document access | `ai-service` fetches bytes from `core-api` with a service JWT |
| M10 | Source of truth | Core owns transactional data; AI/notification own their operational data |
