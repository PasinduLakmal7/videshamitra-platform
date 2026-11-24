# Project Progress

**Last updated:** 2026-11-24
**Current phase:** M0–M4 core backend implemented and security-hardened; M5 admin portal pages in place; AI/notification services, worker web and live-Supabase verification pending
**Team:** 3 people — Person 1 platform/core/admin/infra, Person 2 AI (`ai-service`), Person 3 worker web + Flutter mobile + research
**Mobile app:** Flutter, separate repository (docs/contracts only here)

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
| AI service (`ai-service`) | 🚧 Skeleton, `ai` schema, LLM adapter | `services/ai-service`: health, internal JWT, core client, PII-safe logs; `ai` migrations 001–004 + least-privilege role; Gemini adapter, fake LLM, usage ledger + daily budget; 76 unit + 7 integration tests | Phase 4 guardrails |
| Notification service | ⏸️ Placeholder | `services/notification-service/README.md` | Implement device/preference/delivery |
| Worker web (`web-frontend`) | ⚠️ Vite starter mounted | `main.jsx` renders the template `App.jsx`; TS app is unmounted stubs | Person 3: fix mount, add lint/typecheck to CI |
| Admin portal (`admin-frontend`) | 🚧 Pages implemented | Login, dashboard, cases, agencies, users, audit; `tsc`/build pass | Playwright E2E + live API |
| Database | ✅ Migrations 001–011 + seed | `services/core-api/migrations`; 001–011 verified on Postgres 16 | Live Supabase storage policy check |
| Auth | 🚧 Supabase proxy + JWT verification, hardened | `app/core/security.py`, `app/services/auth_service.py` | Live Supabase login/OTP test |
| Tests | ✅ Unit/contract; integration gated | 100 pass, 1 skipped (needs `TEST_DATABASE_URL`) | Add event round-trip + E2E with stubs |
| CI | ✅ Updated, not yet run on GitHub | `.github/workflows/ci.yml` | Watch first run |
| Infrastructure | 🚧 Compose/Kong valid; core + frontend images build | `docker-compose.yml`, `infra/kong/kong.yml`, nginx-unprivileged frontend images | Full stack with Supabase + workers |

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
| Ownership split | `docs/scope/work-division.md` (local, gitignored) |
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
- [x] Work division updated for 2 people across 3 services (superseded by the 3-person split).
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
- [x] `CORE-45`–`CORE-46` CI rewrite and Compose/Kong (validated config; core image builds).
- [x] Migrations `001`–`010` and demo seed verified against Postgres 15.
- [x] Unit/contract suite: 76 passing, 1 integration test gated on `TEST_DATABASE_URL`.
- [x] Live smoke test against Postgres + Redis: auth/me, dashboard, cases, agencies, users, check-ins, idempotent verification, outbox publish, duplicate AI result, high-risk escalation, case resolve, audit.
- [x] RLS read paths verified as `authenticated`: worker sees only own rows, cannot change own role; staff see all users/cases; audit is admin-only. (Write policies were not covered; direct worker writes were removed in `011`.)
- [x] Core image built; container starts and `/health` responds (readiness correctly 503 without Redis/storage).
- [x] Kong declarative config parses successfully.
- [x] Whole-platform architecture document added (`docs/architecture/system-architecture.md`), linked from README and architecture docs.
- [x] Security audit fixes (critical/high): dev OTP lock-down, insecure-default rejection, `ENVIRONMENT` defaults to production, RLS/storage write lock-down (`011`), OTP/login rate limits fail closed with trusted client IP, stale `pending` recovery with retry cap, check-in consent revoke, SLBFE import source lock-down, internal token lifetime + per-route issuer, chat attachment ownership, hardened frontend images, Compose env fixes, admin session storage.
- [x] 3-person work division, Flutter + FCM mobile docs, ai-service contract (`docs/ai-agents/multi-agent-spec.md`).

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
7. Review the audit fixes on branch `audit-fixes`, then work the security backlog
   below and change requests CR-1…CR-9 (`docs/ai-agents/multi-agent-spec.md`).

### Person 2 — AI (`ai-service`)

1. Phase 4: guardrails (full PII set, prompt-injection wrapping, cited
   findings only, safety footer, output validation with one retry).
2. Consume `verification.requested` from `vm:ai:requests` and publish
   `verification.completed` / `verification.failed` to `vm:ai:results`.
3. Implement `/internal/v1/analyses/{verification_id}` for the admin trace proxy.
4. Implement chat/speech/WhatsApp internal endpoints used by the core proxies.

### Person 3 — worker web, mobile, research

1. Mount the TypeScript app in `web-frontend/` (replace the Vite starter), add
   deps, lint/typecheck, and the CI gate.
2. Build worker flows against `docs/api/openapi.json` (generated types).
3. Start the Flutter app per `docs/mobile/overview.md`.
4. Collect eval datasets (misspelt agencies, labelled ads, si/ta prompts) with Person 2.

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
| Team split | 3 people: P1 platform/core/admin/notification/infra, P2 all AI, P3 worker web + Flutter mobile + research/eval data |
| Mobile stack | Flutter (Dart) + Firebase Cloud Messaging (matches the final proposal) |
| LLM | Gemini (multimodal) behind a provider-neutral adapter in `ai-service` |
| Planning docs | `docs/scope/` (proposals, work division, personal roadmap) and `CLAUDE.md` are local-only and gitignored |
| Environment default | `ENVIRONMENT` defaults to `production`; dev-only features refuse to run elsewhere |
| Dev OTP | Optional `AUTH_DEV_OTP` fallback for worker accounts only; startup fails outside development/test |
| AI/notification Compose | ai-service added (internal network, no ports, no `env_file`, explicit env); notification-service pending |
| ai-service settings | Root `.env` first, then `services/ai-service/.env` overrides it (own `ai_service_role` DSN) |
| LLM | Gemini via `google-genai` behind `LLMClient`; every call through `MeteredLLM` (PII redaction, ledger `ai.llm_usage`, daily token budget fails closed); SDK given an owned `httpx.AsyncClient` (it otherwise picks `httpx2`); FAST tier uses low thinking |
| ai-service DB access | Runtime `DATABASE_URL` = `ai_service_role` (DML on `ai` only); migrations use `MIGRATION_DATABASE_URL` (admin); LangGraph checkpointer `setup()` runs as admin in Phase 8 |

---

## Blockers / open questions

| Item | Status | Owner | Notes |
|---|---|---|---|
| SLBFE source format/access | Open | Person 1 | CSV/JSON importer is ready; use fixtures until the real export is confirmed |
| SMS provider for phone OTP | Open | Person 1 | Supabase phone auth needs a provider/budget; dev OTP fallback exists |
| FCM credentials (Firebase project) | Open | Person 1 / Person 3 | Needed for real push delivery tests |
| Production database separation | Open | Person 1 | Separate schemas locally; separate DBs recommended in production |
| Live Supabase verification | Open | Person 1 | Auth/Storage/RLS not exercised in this environment |
| AI-service detailed task plan | Done (local roadmap) | Person 2 | Contract in `docs/ai-agents/multi-agent-spec.md` |
| Core change requests CR-1…CR-9 | Open | Person 1 (spec: Person 2) | Needed for unable-to-verify, agency search, escalation, drafts, WhatsApp, data rights |
| Security backlog (medium) | Open | Person 1 | Redis password; non-superuser DB role in Compose; atomic WhatsApp dedupe; pypdf off the event loop; soft delete keeps evidence; system escalation must not take drafts; stale idempotency reservations; worker loop crash isolation; caseworkers editing admins; unverified/non-unique phone; staff overturning AI verdicts; seed script env guard; audio MIME fallback; upstream error text; storage path logging; per-peer internal secrets; HttpOnly refresh cookie for admin |
| Notification-service implementation | Pending | Person 1 | Placeholder only; contract frozen |
| Full Compose stack | Pending | Person 1 | Image builds and runs; needs Supabase + worker + AI/notification containers |
| Compose/CI ai-service additions | Review | Person 1 | Commit `build: add ai-service to compose and ci` on `ai/phase-1-skeleton` |
| `/internal/v1/audit-events` accepts any allowed issuer | Open (minor) | Person 1 | Spec says `iss=ai-service` only; other internal routes already enforce it |
| Supabase CLI writes `supabase/.branches/`, `supabase/.temp/` | Open (minor) | Person 1 | Untracked after `supabase start`; consider adding to `.gitignore` |
| `ai_service_role` login/password per environment | Open | Person 1 / Person 2 | Migration keeps it `nologin`; set login + password out of band; `bootstrap.sql` needs no change (ai migration owns schema + grants) |
| Gemini model access (free-tier key) | Open | Person 2 | `gemini-2.5-*` closed to new keys; pro models (`v1beta`) return 429 on this key, so FAST = PRO = `gemini-3.5-flash`; free-tier latency 18–46 s per call puts the < 15 s verdict target at risk; paid key needed for PRO and real data |
| Demo rule data + si/ta wording | Open | Person 2 / Person 3 | `ai.fee_rules`/`wage_floors`/`red_flag_rules` are DEMO (marked in `source`); replace with sourced SLBFE figures; native review of si/ta text |

**Active blockers:** none in code; live Supabase/AI/notification verification requires their runtimes.

---

## Run log

> Newest first. One entry per agent run. Keep it short.

### 2026-11-24 — AI Phase 3: LLM adapter and usage accounting

- **Agent/session:** coding agent (Person 2 session)
- **Scope:** `services/ai-service/app/llm`, PR #2 merge
- **Changed:** PR #2 (phases 0–2) merged to `main` after adding `respx` to core's CI install (core-api job was already failing on `main`); `app/llm/base.py` (`LLMClient`, tiers, errors, PII hook), `gemini.py` (JSON schema output, safety settings, hard timeout, bounded retries with jitter, error mapping and redaction, owned httpx transport, low thinking for FAST), `fake.py` (deterministic, keyed on redacted prompt), `usage.py` (cost estimates, `MeteredLLM` budget guard failing closed, `PgUsageStore`); migration `004_llm_usage.sql`; `scripts/llm_smoke.py`; defaults `gemini-3.5-flash`, `LLM_TIMEOUT_SECONDS=60`
- **Verified:** `ruff`, `pytest -q` 76 passed / 7 skipped (retry path, 429/5xx, bounded attempts, hard timeout, transport timeout, schema failure, blocked prompt, key never in URL or errors, redacted prompt on the wire); integration 7/7 on Postgres 16 and Supabase (runtime role); live smoke: typed `SmokeResult` from `gemini-3.5-flash` (66 in / 87 out); PR #2 CI all 5 jobs green
- **Decisions:** per-call ledger table instead of only `analysis_runs` (chat calls have no run); FAST tier low thinking (46 s → 18.5 s on the same prompt); cost table holds only `gemini-3.5-flash` (USD 1.50 / 9.00 per 1M, Google list price)
- **Blocked:** PRO-tier models need a paid key (see blockers)
- **Next:** Phase 4 (guardrails)

### 2026-11-24 — AI Phase 2: `ai` schema and database access

- **Agent/session:** coding agent (Person 2 session)
- **Scope:** `services/ai-service` migrations, runner, pool
- **Changed:** `migrations/001_ai_foundation.sql` (schema, `ai_service_role` usage + DML with default privileges, no CREATE, no `core`, registry revoked; runs, traces, extractions, dedupe), `002_rules.sql` (fee/wage/red-flag rules with demo seed, en/si/ta), `003_chat.sql` (sessions, messages, retention indexes); `app/db/migrate.py` (checksums, advisory lock, refuses edited files); `app/db/pool.py` (`search_path=ai`, not wired until Phase 7); `MIGRATION_DATABASE_URL`; README; spec §3
- **Verified:** `ruff`, `pytest -q` 52 passed / 6 skipped; migrations twice on throwaway Postgres 16 (3 then 0) and on local Supabase (PG 17); integration 6/6 on both (idempotence, tamper refusal, demo seed, role denied on `core.users`, CREATE and registry, DML allowed, only `*_redacted` text columns, pool `search_path`); `ai_service_role` login checked with psql
- **Decisions:** separate admin migration DSN; on Supabase the isolation test logs in as the role (`TEST_AI_DATABASE_URL`) because `postgres` cannot `SET ROLE`
- **Blocked:** none (demo rule data until sourced figures exist)
- **Next:** Phase 3 (LLM adapter and usage accounting)

### 2026-11-24 — AI Phase 1: ai-service skeleton

- **Agent/session:** coding agent (Person 2 session)
- **Scope:** `services/ai-service` scaffold; Compose/CI additions for Person 1 review
- **Changed:** `pyproject.toml` + pinned `requirements*.txt`; `app/core` (config with `SecretStr` and insecure-secret rejection outside dev/test, JSON logs with PII redaction filter, pure-ASGI request/trace ids, core error envelope, internal JWT verify/mint + `require_core`); `app/guardrails/pii.py` stub (email, NIC, phone); `app/clients/core_api.py` (3 s/15 s timeouts, fresh 60 s token, bounded GET retries, unwraps `{data}`); `/internal/v1/health`; non-root Dockerfile (uid 10001, port 8010); README; Compose `ai-service` (internal only, no ports, no `env_file`); CI `ai-service` job + image build
- **Verified:** `ruff check`, `ruff format --check`, `pytest -q` 47 passed (auth matrix: missing, bad signature, expired, wrong aud/iss, lifetime > 300 s, missing claims, `none` alg); CI install from pinned requirements re-run, 47 passed; `docker build` ok, container uid 10001; `docker compose config -q` ok (no ports, `internal` only); live: ai-service on :8010, core `/ready` → `ai_service: true`. Not verified: GitHub CI run, Compose stack up
- **Decisions:** FastAPI 0.165 hides included routes, so the route-guard test checks every OpenAPI path returns 401 without a token; Gemini defaults `gemini-2.5-flash`/`gemini-2.5-pro` until Phase 3
- **Blocked:** none
- **Next:** Phase 2 (`ai` schema and database access)

### 2026-11-24 — AI Phase 0: local setup and orientation

- **Agent/session:** coding agent (Person 2 session)
- **Scope:** local environment, contract review
- **Changed:** `docs/ai-agents/multi-agent-spec.md` §4.3 notes core internal responses use the `{data, meta}` envelope; local `.env` (Supabase keys, `GEMINI_API_KEY`; untracked)
- **Verified:** `supabase start`, `bootstrap.sql`, migrations 001–011 (second run no-op), demo seed; core `pytest` 100 passed / 1 skipped; Redis + core + worker on host; `/health` 200, `/ready` 200; Gemini key lists models
- **Decisions:** none
- **Blocked:** none
- **Next:** Phase 1 skeleton

### 2026-11-22 — Security audit fixes, doc alignment, 3-person split

- **Agent/session:** coding agent (Person 2 session)
- **Scope:** core-api security (critical/high), infra, admin client, docs
- **Changed:** `config.py` (production default, insecure-default rejection, dev-only guards); `auth_service.py` (dev OTP worker-only + audited, no code in responses, fail-closed OTP limits, login limit); `entities.py` (last XFF hop); migration `011_security_hardening.sql` (drop worker write policies on core tables and storage); stale `pending` recovery with `MAX_VERIFICATION_RETRIES`; consent-aware check-in queries; SLBFE import uses only `SLBFE_SOURCE_URL`, no redirects; internal tokens need `iat`, ≤ 300 s, AI-only routes require `iss=ai-service`; chat `session_id`/attachments are UUIDs and attachments must be the caller's documents; frontend Dockerfiles → multi-stage nginx-unprivileged with CSP; orphan `infra/docker/*` removed; Compose uses `DOCKER_*` URLs and requires `INTERNAL_JWT_SECRET`/`ENVIRONMENT`; CI sets `ENVIRONMENT=test`, read-only token, builds frontend images; admin session in `sessionStorage`; `.gitignore` (`.env.*`, `docs/scope/`, `CLAUDE.md`); docs (README, mobile → Flutter + FCM, architecture, API, schema, contracts, Kong, agent rules, AI contract)
- **Verified:** core `pytest` 100 passed / 1 skipped; `ruff check` + `format --check`; OpenAPI regenerated and admin types regenerated; contracts current; migrations 001–011 applied twice on Postgres 16 + integration test; changed SQL executed against Postgres; admin `lint`/`typecheck`/`build`; admin + web images built, admin container checked (uid 101, SPA fallback, CSP headers); `docker compose config`. Not verified: live Supabase Auth/Storage, GitHub CI run
- **Decisions:** Flutter + FCM; Gemini; 3-person split; `docs/scope/` local-only; medium findings moved to Person 1 backlog
- **Blocked:** none
- **Next:** Person 1 reviews branch `audit-fixes`; Person 2 starts the ai-service skeleton

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
