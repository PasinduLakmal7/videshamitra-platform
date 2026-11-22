# Project Progress

**Last updated:** 2026-11-22
**Current phase:** M0–M4 core backend implemented; M5 admin portal pages in place; AI/notification services and live-Supabase verification pending
**Team:** 2 people across 3 services
**Mobile app:** separate repository (docs/contracts only here)

> This document is updated after **every agent run**. See [`agent-rules.md`](../agent-rules.md) for the mandatory update rules.
>
> Update only the sections relevant to the run. Do not bulk-rewrite unrelated statuses.

---

## Status at a glance

| Area | Status | Evidence / location | Next |
|---|---|---|---|
| Documentation & architecture | ✅ Done for current phase | `docs/architecture/system-architecture.md`, `microservices.md`, `docs/core-api-plan.md`, `docs/api/openapi.json` | Keep in sync with code |
| Repo restructure | ✅ Done | `services/core-api/`, `packages/contracts/`; `web-backend/` removed | — |
| Core API (`core-api`) | 🚧 Implemented; live integration pending | `services/core-api/app`, 65 OpenAPI paths | Verify against Supabase Auth/Storage; AI/notification stubs |
| AI service (`ai-service`) | ⏸️ Not started | Person 2 | Consume `verification.requested.v1` |
| Notification service | ⏸️ Placeholder | `services/notification-service/README.md` | Implement device/preference/delivery |
| Worker web (`web-frontend`) | ⏸️ Scaffold only | Vite scaffold; pages empty | Person 2 |
| Admin portal (`admin-frontend`) | 🚧 Pages implemented | Login, dashboard, cases, agencies, users, audit; `tsc`/build pass | Playwright E2E + live API |
| Database | ✅ Migrations 001–010 + seed | `services/core-api/migrations`, verified on Postgres 15 | RLS verification under `authenticated` |
| Auth | 🚧 Supabase proxy + JWT verification | `app/core/security.py`, `app/services/auth_service.py` | Live Supabase login/OTP test |
| Tests | ✅ Unit/contract; integration gated | 76 pass, 1 skipped (needs `TEST_DATABASE_URL`) | Add event round-trip + E2E with stubs |
| CI | ✅ Updated, not yet run on GitHub | `.github/workflows/ci.yml` | Watch first run |
| Infrastructure | 🚧 Compose/Kong valid; image builds | `docker-compose.yml`, `infra/kong/kong.yml`, image health check verified | Full stack with Supabase + workers |

**Legend:** ✅ done · 🚧 in progress · ⏸️ planned/scaffold · ⚠️ needs attention · ⛔ blocked · 📄 external

---

## Current state

- The three-service architecture is in place; **only `core-api` is public**.
- `services/core-api/` now contains a working FastAPI service:
  - `core` migrations 001–010, RLS, storage policies, indexes, and an
    idempotent migration runner.
  - asyncpg pool, Redis streams, transactional outbox + relay, consumer dedupe,
    dead-letter handling, and short-lived internal service JWTs.
  - Supabase JWT verification (JWKS + HS256 fallback), role guards, envelopes,
    pagination, request IDs, and DB-backed idempotency.
  - Auth proxy, users/consents, agencies + SLBFE import + watchdog,
    documents/storage, verification orchestration + AI result consumer,
    journeys/check-ins/scheduler/escalation, in-app notifications + delivery
    requests + device/preference proxy, complaints/cases/admin APIs, audit.
  - Chat/speech proxying and signed WhatsApp webhook forwarding to ai-service.
- `packages/contracts/` holds generated event JSON Schemas; OpenAPI is in
  `docs/api/openapi.json` with generated admin types.
- `admin-frontend/` has a working login/dashboard/cases/case detail/agencies/
  users/audit UI against the core API (typecheck + build pass).
- `services/notification-service/` is a documented placeholder; `ai-service` is
  Person 2's deployable.
- The worker mobile app remains in a separate repository.
- Live Supabase Auth/Storage, AI/notification stubs, the full Compose stack, and
  Playwright E2E have **not** been verified in this environment.

### Source of truth

| Topic | Document |
|---|---|
| Service boundaries, data ownership, events | `docs/architecture/microservices.md` |
| Core API tasks and contracts | `docs/core-api-plan.md` |
| Ownership split | `docs/work-division.md` |
| Public API | `docs/api/endpoints.md` |
| Database schemas | `docs/database/schema.md` |
| AI service | `docs/ai-agents/multi-agent-spec.md` |
| Mobile contract | `docs/mobile/overview.md` |
| Agent operating rules | `agent-rules.md` |

---

## Completed

- [x] Three-service architecture defined (`core-api`, `ai-service`, `notification-service`).
- [x] Data ownership, event flows, auth, and deployment topology documented.
- [x] Core API implementation plan written with 50 tasks (`CORE-01` → `CORE-50`).
- [x] Work division updated for 2 people across 3 services.
- [x] README, API, database, AI, Kong, and architecture docs aligned to the service model.
- [x] Mobile app documented as a separate repository.
- [x] Agent rules created.
- [x] Progress tracking created and linked.
- [x] `CORE-01` repo restructure: `web-backend/` → `services/core-api/`; contracts package; notification placeholder.
- [x] `CORE-02`–`CORE-08` foundation: config, asyncpg/Redis, migration runner, health/readiness, envelopes/errors/pagination/idempotency, OpenAPI/contracts export, outbox relay, internal JWT/clients.
- [x] `CORE-09`–`CORE-16` identity/agencies: Supabase token verification, auth proxy, profiles/consents, audit, agency search, SLBFE parser/importer, license watchdog.
- [x] `CORE-17`–`CORE-23` documents/verification: storage client, upload validation, signatures, verification state machine, AI result consumer, internal document/agency endpoints, admin review/trace.
- [x] `CORE-24`–`CORE-27` journeys/check-ins: consent scheduling, responses, overdue view, scheduler, missed escalation.
- [x] `CORE-28`–`CORE-33` notifications/complaints/cases: in-app feed, delivery requests, device/preference proxies, complaint drafts/submission/evidence, case notes/escalation.
- [x] `CORE-34`–`CORE-35` dashboard, users, audit admin APIs.
- [x] `CORE-36`–`CORE-38` chat/speech/WhatsApp proxies and admin AI trace proxy.
- [x] `CORE-39`–`CORE-43` admin portal shell, login, dashboard, cases, case detail, agencies, users, audit.
- [x] `CORE-45`–`CORE-46` CI rewrite and Compose/Kong (validated config; image build pending).
- [x] Migrations `001`–`010` and demo seed verified against Postgres 15.
- [x] Unit/contract suite: 76 passing, 1 integration test gated on `TEST_DATABASE_URL`.
- [x] Live smoke test against Postgres + Redis: auth/me, dashboard, cases, agencies, users, check-ins, idempotent verification, outbox publish, duplicate AI result, high-risk escalation, case resolve, audit.
- [x] RLS verified as `authenticated`: worker sees only own rows, cannot change own role; staff see all users/cases; audit is admin-only.
- [x] Core image built; container starts and `/health` responds (readiness correctly 503 without Redis/storage).
- [x] Kong declarative config parses successfully.
- [x] Whole-platform architecture document added (`docs/architecture/system-architecture.md`), linked from README and architecture docs.

---

## In progress

- **Core live integration:** verify Supabase Auth (email + phone OTP), Storage
  upload/signed URLs, and RLS policies against the real local stack.
- **Admin E2E:** Playwright flow (login → dashboard → case queue → case detail →
  note → escalate → audit) with seeded data.
- **AI/notification stubs:** wire Compose/integration tests and complete the
  verification round trip with an AI stub.
- **Docker image:** the core image builds and starts (health verified);
  run the full Compose stack with a live Supabase stack and the worker.

---

## Next actions

### Person 1 — core platform

1. Start local Supabase, run `supabase/bootstrap.sql`, migrations, and seed; test
   staff email login and worker OTP end to end.
2. Upload a real PDF/JPEG to Storage; verify signed download and duplicate
   rejection; check `documents` bucket policies.
3. Run the migration integration test with `TEST_DATABASE_URL` and verify RLS as
   `authenticated` (worker cannot read another worker's rows).
4. Add the notification-service implementation (devices, preferences, delivery)
   against the frozen `notification.requested.v1` contract.
5. Add Playwright E2E for the admin portal.
6. Build the core image and run `docker compose up --build`; add AI/notification
   containers when their scaffolds land.

### Person 2 — AI and worker web

1. Consume `verification.requested.v1` from `vm:ai:requests` and publish
   `verification.completed.v1` / `verification.failed.v1` to `vm:ai:results`.
2. Implement `/internal/v1/analyses/{verification_id}` for the admin trace proxy.
3. Implement chat/speech internal endpoints used by the core proxies.
4. Scaffold the worker web against `docs/api/openapi.json`.

### Shared

1. Run the verification vertical slice end to end with AI/notification stubs.
2. Validate the event schemas in CI (`scripts/export_contracts.py --check`).
3. Complete the release smoke test (`CORE-50`).

---

## Decisions

| Decision | Choice |
|---|---|
| Service split | `core-api`, `ai-service`, `notification-service` |
| Public API | `core-api` only, behind Kong |
| Data access | `asyncpg` + explicit SQL; service-owned schemas |
| Identity | Supabase Auth; core verifies public JWTs |
| Internal auth | Short-lived service JWTs |
| Async work | Redis Streams + transactional outbox + idempotent consumers |
| AI execution | Async jobs; AI-service publishes results |
| Notification delivery | `notification-service`; core owns in-app feed only |
| Complaints/cases | `core-api` |
| Check-ins + agency watchdog | `core-api` workers |
| Chat/speech | `core-api` proxies to `ai-service` |
| Mobile | Separate repository; docs only here |
| Contract source | Pydantic models in `app/events/schemas.py`; JSON Schemas generated into `packages/contracts` |
| Admin auth | `admin-frontend` logs in through `core-api /auth/login`; tokens stay in the core API client (no direct Supabase browser SDK) |
| Admin data layer | Typed `fetch` client + local hooks instead of TanStack Query (smaller surface for WS8) |
| Dev OTP | Optional `AUTH_DEV_OTP` fallback, refused in production |
| AI/notification Compose | Not yet included; their owners add containers to the internal network |

---

## Blockers / open questions

| Item | Status | Owner | Notes |
|---|---|---|---|
| SLBFE source format/access | Open | Person 1 | CSV/JSON importer is ready; use fixtures until the real export is confirmed |
| SMS provider for phone OTP | Open | Person 1 | Supabase phone auth needs a provider/budget; dev OTP fallback exists |
| Expo push credentials | Open | Person 1 | Needed for real push delivery tests |
| Production database separation | Open | Person 1 | Separate schemas locally; separate DBs recommended in production |
| Live Supabase verification | Open | Person 1 | Auth/Storage/RLS not exercised in this environment |
| AI-service detailed task plan | Pending | Person 2 | Core contracts are frozen |
| Notification-service implementation | Pending | Person 1 | Placeholder only; contract frozen |
| Full Compose stack | Pending | Person 1 | Image builds and runs; needs Supabase + worker + AI/notification containers |

**Active blockers:** none in code; live Supabase/AI/notification verification requires their runtimes.

---

## Run log

> Newest first. One entry per agent run. Keep it short.

### 2026-11-22 — Whole-platform architecture document

- **Agent/session:** coding agent
- **Scope:** architecture documentation
- **Changed:** added `docs/architecture/system-architecture.md` (context, layers, services, flows, data ownership, security/trust zones, deployment, failure modes, observability, scaling, decisions, status, evolution); linked it from `README.md`, `docs/architecture/overview.md`, and `microservices.md`; removed the ignored work-division link from the overview
- **Verified:** markdown links checked; no code tests run (docs-only)
- **Decisions:** the new document is the broad system view; `microservices.md` remains the service/event deep dive
- **Blocked:** none
- **Next:** keep the status and architecture docs aligned as `ai-service` and `notification-service` land

### 2026-11-22 — Core API implementation (M0–M5 backend, admin portal)

- **Agent/session:** coding agent
- **Scope:** `CORE-01` → `CORE-48` (core service, contracts, infra, admin portal); `CORE-49`/`CORE-50` partial
- **Changed:** moved `web-backend/` → `services/core-api/`; added migrations 001–010, full FastAPI app (auth, users, agencies, documents, verification, journeys, check-ins, notifications, complaints, admin, chat, webhooks, internal routes); outbox/consumer/workers; SLBFE importer + demo seed; OpenAPI + event schemas + admin TS types; Compose/Kong/CI; admin portal pages; README/docs
- **Verified:** migrations + seed run twice on Postgres 15 (Podman); RLS matrix as `authenticated`; live smoke against Postgres+Redis (auth/me, dashboard, cases, agencies, users, check-ins, idempotent verification, outbox publish, duplicate AI result dedupe, internal service JWT, high-risk escalation, case resolve, audit); core image built and `/health` verified in a container; Kong config parses; 76 unit/contract tests pass, 1 migration test gated on `TEST_DATABASE_URL` (passes when set); `ruff check`/`format --check`; `compose config`; admin `tsc` + `eslint` + `vite build`; web-frontend build. Not verified: live Supabase Auth/Storage, AI/notification stubs, full Compose stack, Playwright E2E
- **Decisions:** Pydantic is the event-contract source; admin logs in through core `/auth/login` with a typed fetch client; optional dev OTP fallback; AI/notification Compose containers deferred to their owners; Supabase splits internal (server) and public (signed URL) URLs for Docker
- **Blocked:** none in code
- **Next:** run local Supabase + core + stubs end to end and add notification-service implementation

### 2026-11-22 — Agent rules and progress tracking

- **Agent/session:** coding agent
- **Scope:** repository documentation
- **Changed:** added `agent-rules.md`; added `docs/progress.md`; linked progress/agent rules from `README.md`, `docs/core-api-plan.md`, `docs/work-division.md`, and `docs/person-1-plan.md`
- **Verified:** markdown links resolve; fenced blocks balanced; no code tests run (docs-only)
- **Decisions:** progress must be updated after every run; only affected sections are updated
- **Blocked:** none
- **Next:** `CORE-01` service restructure

### 2026-11-22 — Microservice architecture pivot and plans

- **Agent/session:** coding agent
- **Scope:** architecture and planning
- **Changed:** added `docs/architecture/microservices.md` and `docs/core-api-plan.md`; rewrote `docs/work-division.md` for 2 people / 3 services; updated README, architecture overview, API, database, AI spec, Kong docs; replaced the old monolith plan with a Person 1 index
- **Verified:** markdown link check passed; no code tests run (docs-only)
- **Decisions:** three services; core-api public; AI and notification internal; Redis Streams/outbox; complaints/check-ins/watchdog in core; notification delivery separate; mobile external
- **Blocked:** none
- **Next:** `CORE-01` service restructure

---

## Progress update template

Copy this into the run log after each run:

```markdown
### YYYY-MM-DD — <short scope>

- **Agent/session:** <name or "coding agent">
- **Scope:** <service/area, task IDs>
- **Changed:** <files or features>
- **Verified:** <tests/lint/manual checks; say "none" if no code changed>
- **Decisions:** <only if applicable>
- **Blocked:** <blocker or "none">
- **Next:** <single next action>
```
