# VideshaMitra Architecture Overview

VideshaMitra is a multilingual, agentic AI migration-safety companion designed to protect Sri Lankan workers before, during, and after migration.

> **This repository uses three services:** `core-api`, `ai-service`, and `notification-service`. See [`microservices.md`](microservices.md) for boundaries, data ownership, events, and deployment.

## Services

| Service | Responsibility | Public |
|---|---|---|
| `core-api` | Auth/users, agencies/SLBFE, verification orchestration, documents, journeys, check-ins, complaints/cases, in-app notifications, admin, audit, chat proxy | **Yes** via Kong |
| `ai-service` | LangGraph, OCR, LLM (Gemini), speech, chat sessions, AI traces, checkpoints (planned) | No |
| `notification-service` | Device tokens, preferences, FCM/WhatsApp delivery, retries, delivery status (planned) | No |
| Kong | Public gateway, CORS, rate limits | Edge |
| Supabase | Postgres, Auth, Storage | Infrastructure |
| Redis | Event streams / async jobs | Infrastructure |

## Clients and channels

| Channel | Users | Calls |
|---|---|---|
| Worker mobile app (Flutter, separate repo) | Migrant workers | Kong → `core-api` |
| Worker web portal | Migrant workers | Kong → `core-api` |
| Admin portal | Caseworkers and admins | Kong → `core-api` |
| WhatsApp webhook | Workers | Kong → `core-api` (proxied to `ai-service` where needed) |

No client calls `ai-service` or `notification-service` directly.

## Data ownership

| Data | Owner |
|---|---|
| Users, consents, agencies, verifications, document metadata, journeys, check-ins, complaints, in-app notifications, audit | `core-api` (`core` schema) |
| OCR text, agent traces, chat sessions/messages, LangGraph checkpoints | `ai-service` (`ai` schema) |
| Device tokens, preferences, delivery attempts/status | `notification-service` (`notification` schema) |
| Auth identities, document blobs | Supabase Auth / Storage |

Services reference each other by ID only. There are no cross-schema joins or foreign keys.

## Communication

- **Synchronous internal REST** for fast calls and streaming: chat, speech, device/preference management, AI trace lookup.
- **Asynchronous events** on Redis Streams for verification jobs and notification fan-out.
- **Transactional outbox** in `core-api` for reliable publishing; consumers are idempotent by `event_id`.
- **Internal auth** uses short-lived service JWTs; public auth uses Supabase JWTs.

## Deployment

- Local: Kong + `core-api` + `core-api-worker` + Redis in Compose, with Supabase via CLI. `ai-service` and `notification-service` join the internal network when they are built.
- Production: one container per process, managed Postgres/Redis, Kong as the only public entry point.
- Only `core-api` is exposed through Kong. Other services live on an internal network.

## Detailed documentation

- [System architecture](system-architecture.md) — whole-platform view: context,
  flows, data, security, deployment, reliability, status
- [Microservice architecture](microservices.md) — boundaries, ownership, events
- [Core API plan](../core-api-plan.md)
- [API endpoints](../api/endpoints.md)
- [Database schema](../database/schema.md)
- [Multi-agent specification](../ai-agents/multi-agent-spec.md)
- [Worker mobile app](../mobile/overview.md)
